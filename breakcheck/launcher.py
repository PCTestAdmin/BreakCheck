"""Desktop launch options shared by the Explorer integration and packaged app."""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


def launch_paths(inspect=None, root=None):
    """Choose a conservative initial scan scope; never start a scan automatically."""
    target = Path(inspect).expanduser().absolute() if inspect else None
    if target is not None and not target.exists():
        raise ValueError('The selected file or folder no longer exists.')
    scope = Path(root).expanduser().resolve(strict=True) if root else (target.parent.resolve() if target else None)
    if scope is not None and not scope.is_dir():
        raise ValueError('Scan root must be a directory.')
    if target is not None and scope is not None and not target.resolve().is_relative_to(scope):
        raise ValueError('The selected target is outside the scan root.')
    return scope, target


def run_desktop(inspect=None, root=None, self_test=False, background=False):
    from .gui import App
    from .core import scan, analyze
    from .tray import WindowsInstance
    instance = None if self_test else WindowsInstance()
    if instance is not None and not instance.primary:
        try:
            if not background or inspect or root:
                instance.forward(inspect, root)
            return 0
        finally:
            instance.close()
    try:
        app = App(self_test=self_test)
    except BaseException:
        if instance is not None:
            instance.close()
        raise
    if self_test:
        app.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory).resolve() / 'project'
                folder.mkdir()
                asset = folder / 'asset.png'
                asset.write_bytes(b'demo')
                (folder / 'index.html').write_text('<img src="asset.png">', encoding='utf-8')
                report = analyze(scan(folder), asset)
                app.render(report)
                app.update_idletasks()
                if not app.insights.canvas.find_all():
                    raise RuntimeError('Graph self-test failed.')
                app.dark.set(True)
                from .views import apply_theme
                apply_theme(app, True)
                app.update_idletasks()
                if len(report.direct) != 1 or len(app.tree.get_children()) != 1:
                    raise RuntimeError('Desktop self-test failed.')
                from .safety import SafetyIndex, duplicates
                state = SafetyIndex(Path(directory) / 'state' / 'safety.sqlite3')
                (folder / 'copy.png').write_bytes(b'demo')
                state.refresh(folder)
                asset.rename(folder / 'moved.png')
                app.safety.render_snapshot(folder, state.refresh(folder))
                from .smart import smart_duplicates
                from .recovery import RecoveryStore
                app.safety.render_duplicates(folder, smart_duplicates(folder))
                vault = RecoveryStore(Path(directory) / 'state' / 'recovery.sqlite3')
                capture = vault.capture(folder)
                app.recovery.render_capture(capture, vault.versions())
                if capture.saved != 3 or len(app.recovery.tree.get_children()) != 3:
                    raise RuntimeError('Recovery workspace self-test failed')
                from .repair import plan_repair, RepairJournal, suggestions
                plan = plan_repair(folder,'index.html','asset.png','moved.png')
                if len(suggestions(folder,state.db)) != 1:
                    raise RuntimeError('Repair suggestion failed')
                app.repair.render_plan(plan)
                journal = RepairJournal(Path(directory) / 'state' / 'repairs.sqlite3')
                ident = journal.apply(plan,plan.token)
                if b'moved.png' not in (folder / 'index.html').read_bytes():
                    raise RuntimeError('Repair apply failed')
                journal.undo(ident)
                if (folder / 'index.html').read_bytes() != plan.before:
                    raise RuntimeError('Repair undo failed')
                for page in app.tabs.pages:
                    app.tabs.select(page)
                    app.update_idletasks()
                app.tabs.select(app.safety.frame)
                if app.tabs.select() != str(app.safety.frame) or app.safety.metrics['files'].get() != '3':
                    raise RuntimeError('Workspace navigation or overview metrics failed')
                app.update_idletasks()
                if len(app.safety.alerts.get_children()) != 1 or len(app.safety.dupes.get_children()) != 2:
                    raise RuntimeError('Safety Center self-test failed.')
                import os, sys
                if os.name == 'nt' and getattr(sys, 'frozen', False):
                    import pystray
                    from .agent import Wakeup
                    if not pystray.Icon.HAS_NOTIFICATION:
                        raise RuntimeError('Packaged Windows notification backend missing')
                    wake = Wakeup(folder)
                    try:
                        if wake.backend != 'events + reconciliation':
                            raise RuntimeError('Packaged Windows filesystem event backend missing')
                        (folder / 'event-test.txt').write_text('test', encoding='utf-8')
                        if not wake.dirty.wait(10):
                            raise RuntimeError('Windows filesystem event not received')
                    finally:
                        wake.close()
                    old = os.environ.get('BREAKCHECK_STATE_DIR')
                    os.environ['BREAKCHECK_STATE_DIR'] = str(Path(directory) / 'instance-test')
                    first = second = None
                    try:
                        first = WindowsInstance()
                        second = WindowsInstance()
                        if not first.primary or second.primary:
                            raise RuntimeError('Windows single-instance guard failed')
                        second.forward(asset)
                        if first.take() != {'inspect': str(asset), 'root': None}:
                            raise RuntimeError('Windows launch forwarding failed')
                    finally:
                        if second is not None:
                            second.close()
                        if first is not None:
                            first.close()
                        if old is None:
                            os.environ.pop('BREAKCHECK_STATE_DIR', None)
                        else:
                            os.environ['BREAKCHECK_STATE_DIR'] = old
        finally:
            app.destroy()
        return 0
    try:
        scope, target = launch_paths(inspect, root)
        if scope is not None:
            app.root_path.set(str(scope))
        if target is not None:
            app.target.set(str(target))
            app.tabs.select(app.impact_tab)
            app.status.set('Choose a wider scan folder if needed, then click Analyze impact. Only the selected scan folder is searched.')
    except (OSError, ValueError) as exc:
        app.status.set(str(exc))
    from .tray import WindowsTray
    app.tray = WindowsTray(app, background=background and not inspect)
    if app.tray.icon is None:
        app.protocol('WM_DELETE_WINDOW', app.tray.quit)
    app.safety.resume()
    def receive_request():
        try:
            request = instance.take() if instance is not None else None
            if request is not None:
                app.deiconify()
                app.lift()
                if request.get('inspect') or request.get('root'):
                    scope, target = launch_paths(request.get('inspect'), request.get('root'))
                    if scope is not None:
                        app.root_path.set(str(scope))
                    if target is not None:
                        app.target.set(str(target))
                        app.tabs.select(app.impact_tab)
        except (OSError, ValueError) as exc:
            app.status.set(str(exc))
        app.after(500, receive_request)
    app.after(500, receive_request)
    try:
        app.mainloop()
    finally:
        app.safety.shutdown()
        if instance is not None:
            instance.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='BreakCheck desktop application')
    parser.add_argument('--inspect', help='Preselect a file or folder')
    parser.add_argument('--root', help='Initial scan folder')
    parser.add_argument('--self-test', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--background', action='store_true', help='Start in the Windows notification area')
    args = parser.parse_args(argv)
    return run_desktop(args.inspect, args.root, args.self_test, args.background)
