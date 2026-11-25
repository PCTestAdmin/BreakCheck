"""Bounded Windows package integration tests; run on a disposable CI machine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import winreg

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / 'smoke-logs'
KEYS = (r'Software\Classes\*\shell\BreakCheck.Inspect',
        r'Software\Classes\Directory\shell\BreakCheck.Inspect',
        r'Software\Classes\*\shell\BreakCheck.Guard')


def log(message):
    print(message, flush=True)


def run(label, args, expected=0, timeout=45, capture=False, env=None):
    log(f'START: {label} (timeout {timeout}s)')
    out = subprocess.PIPE if capture else None
    with subprocess.Popen([str(arg) for arg in args], cwd=ROOT, env=env,
                          stdout=out, stderr=subprocess.STDOUT if capture else None,
                          text=True, encoding='utf-8', errors='replace') as proc:
        try:
            result, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill the entire process tree (including PyInstaller children).
            try:
                subprocess.run(['taskkill.exe', '/PID', str(proc.pid), '/T', '/F'],
                               timeout=10, check=False, capture_output=True)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=10)
            raise RuntimeError(f'{label} timed out after {timeout}s')
        if proc.returncode != expected:
            if result:
                log(result)
            raise RuntimeError(f'{label}: exit code {proc.returncode}, expected {expected}')
    log(f'PASS: {label}')
    return result


def gui_test(exe, label):
    path = LOGS / f'{label}.txt'
    env = dict(os.environ, BREAKCHECK_SELF_TEST_LOG=str(path))
    try:
        run(label, [exe, '--self-test'], env=env, timeout=60)
    finally:
        if path.exists():
            log(f'{label} diagnostics:\n{path.read_text(encoding="utf-8")}')
    if not path.exists() or path.read_text(encoding='utf-8').strip() != 'PASS':
        raise RuntimeError(f'{label} did not write a success marker')


def exists_key(key):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            return True
    except FileNotFoundError:
        return False


def wait_removed(app, timeout=45):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not app.exists() and not any(exists_key(key) for key in KEYS):
            return
        time.sleep(0.5)
    raise RuntimeError('Uninstall did not remove the app and Explorer registration')


def main():
    LOGS.mkdir(exist_ok=True)
    # Refuse to disturb an existing installation.
    if any(exists_key(key) for key in KEYS):
        raise RuntimeError('Existing BreakCheck Explorer integration; use a clean runner')
    version = run('source version', [sys.executable, '-m', 'breakcheck', '--version'], capture=True).strip()
    cli = ROOT / 'dist' / 'BreakCheckCLI.exe'
    reported = run('packaged CLI version', [cli, '--version'], capture=True).strip()
    if reported != version:
        raise RuntimeError(f'CLI version mismatch: {reported!r} != {version!r}')
    result = run('packaged CLI dependency scan',
                 [cli, 'check', 'examples/demo', 'assets/logo.svg', '--json'],
                 expected=2, capture=True)
    if len(json.loads(result)['direct']) != 3:
        raise RuntimeError('Unexpected dependency count')
    headless_env = dict(os.environ, BREAKCHECK_STATE_DIR=str(LOGS / 'headless-test-state'))
    headless = run('packaged headless snapshot', [cli, 'watch', 'examples/demo', '--once', '--json', '--poll'], capture=True, env=headless_env)
    if json.loads(headless)['files'] < 1:
        raise RuntimeError('Packaged headless snapshot failed')
    with tempfile.TemporaryDirectory(prefix='BreakCheck Recovery ') as tmp:
        project = Path(tmp).resolve()
        original = project / 'original.txt'
        original.write_bytes(b'recovery smoke test')
        run('packaged recovery capture', [cli, 'recovery', 'capture', project], capture=True, env=headless_env)
        rows = json.loads(run('packaged recovery list', [cli, 'recovery', 'list', '--folder', project], capture=True, env=headless_env))
        original.unlink()
        run('packaged recovery restore', [cli, 'recovery', 'restore', rows[0]['id'], original], env=headless_env)
        if original.read_bytes() != b'recovery smoke test':
            raise RuntimeError('Packaged recovery restore mismatch')
        run('packaged recovery no overwrite', [cli, 'recovery', 'restore', rows[0]['id'], original], expected=1, env=headless_env)
        plan = json.loads(run('packaged guard preview', [cli, 'guard', 'preview', project, 'original.txt', '--destination', 'moved.txt'], capture=True, env=headless_env))
        run('packaged guarded move', [cli, 'guard', 'apply', project, 'original.txt', '--destination', 'moved.txt', '--confirm', plan['confirm']], env=headless_env)
        if original.exists() or (project / 'moved.txt').read_bytes() != b'recovery smoke test':
            raise RuntimeError('Guarded move content mismatch')
    storage = json.loads(run('packaged storage scan', [cli, 'storage', 'examples/demo', '--json'], capture=True, env=headless_env))
    if not storage['complete'] or storage['files'] < 1 or storage['logical_bytes'] <= 0:
        raise RuntimeError('Packaged storage scan failed')
    gui_test(ROOT / 'dist' / 'BreakCheck.exe', 'portable-gui')
    # A source launcher check must never prompt or install packages.
    run('source launcher', ['cmd.exe', '/d', '/c', 'Start-BreakCheck.cmd', '--check'])
    with tempfile.TemporaryDirectory(prefix='BreakCheck Smoke ') as tmp:
        install = Path(tmp) / 'app'
        app = install / 'BreakCheck.exe'
        setup = ROOT / 'release' / 'BreakCheck-Setup.exe'
        try:
            run('silent installer', [setup, '/VERYSILENT', '/SUPPRESSMSGBOXES',
                '/NORESTART', '/SP-', f'/DIR={install}', '/TASKS=explorer',
                f'/LOG={LOGS / "install.log"}'], timeout=90)
            if not app.is_file():
                raise RuntimeError(f'Installed application missing: {app}')
            for key in KEYS:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key + r'\command') as reg:
                    command = winreg.QueryValueEx(reg, '')[0]
                    expected = f'"{app}" --guard --inspect="%1"' if key.endswith('.Guard') else f'"{app}" --inspect="%1"'
                    if command != expected:
                        raise RuntimeError(f'Unexpected Explorer command: {command!r}')
            log('PASS: Explorer registration')
            gui_test(app, 'installed-gui')
        finally:
            uninstaller = install / 'unins000.exe'
            if uninstaller.exists():
                run('silent uninstall', [uninstaller, '/VERYSILENT', '/SUPPRESSMSGBOXES',
                    '/NORESTART', f'/LOG={LOGS / "uninstall.log"}'], timeout=90)
                wait_removed(app)
    log('PASS: all Windows package smoke tests')
    return 0


if __name__ == '__main__':
    sys.exit(main())
