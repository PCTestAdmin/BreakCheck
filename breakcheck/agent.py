"""Headless monitoring, durable preferences and optional event-driven wakeups."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import tempfile
import threading
import time

from .core import SKIP_DIRS, inside
from .safety import SafetyIndex, state_path
from .smart import smart_duplicates
from .recovery import RecoveryStore, MIB


@dataclass
class Preferences:
    root: str = ''
    notifications: bool = True
    backup: bool = False
    quota_mib: int = 256
    auto_updates: bool = False


def settings_path():
    return state_path().parent / 'preferences.json'


def read_preferences(path=None):
    path = Path(path) if path is not None else settings_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return Preferences()
    if not isinstance(data, dict) or not isinstance(data.get('root', ''), str) or not isinstance(data.get('notifications', True), bool):
        raise ValueError('Invalid BreakCheck preferences.')
    backup, quota = data.get('backup', False), data.get('quota_mib', 256)
    if not isinstance(backup, bool) or type(quota) is not int or not 1 <= quota <= 4096:
        raise ValueError('Invalid recovery preferences.')
    auto = data.get('auto_updates', False)
    if not isinstance(auto,bool):
        raise ValueError('Invalid update preference.')
    return Preferences(data.get('root', ''), data.get('notifications', True), backup, quota, auto)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=True)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)


def save_preferences(prefs, path=None):
    write_json(settings_path() if path is None else path, asdict(prefs))


def validated_root(root):
    path = Path(root).expanduser().resolve(strict=True)
    state = state_path().resolve().parent
    if not path.is_dir() or inside(state, path) or inside(path, state):
        raise ValueError('Choose an existing project folder outside the BreakCheck data directory. Use Check now for a drive-wide storage overview.')
    if path == Path(path.anchor):
        raise ValueError('Continuous monitoring requires a project folder, not an entire drive. Use Check now for a storage overview.')
    return path


class Wakeup:
    """Events are hints; periodically reconcile even if the OS misses events."""
    def __init__(self, root, interval=60, use_events=True):
        self.root = Path(root)
        self.interval = interval
        self.dirty = threading.Event()
        self.observer = None
        self.backend = 'polling'
        if use_events:
            self.start_events()

    def mark(self, event_type, path):
        if event_type not in {'created', 'deleted', 'modified', 'moved'}:
            return
        try:
            parts = Path(path).relative_to(self.root).parts
        except ValueError:
            return
        if not any(part in SKIP_DIRS for part in parts):
            self.dirty.set()

    def start_events(self):
        observer = None
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
            owner = self
            class Handler(FileSystemEventHandler):
                def on_any_event(self, event):
                    owner.mark(event.event_type, event.src_path)
                    if getattr(event, 'dest_path', ''):
                        owner.mark(event.event_type, event.dest_path)
            observer = Observer()
            observer.schedule(Handler(), str(self.root), recursive=True)
            observer.start()
            self.observer = observer
            self.backend = 'events + reconciliation'
        except (ImportError, OSError, RuntimeError):
            if observer is not None and observer.is_alive():
                observer.stop()
                observer.join(timeout=3)

    def close(self):
        if self.observer is not None:
            self.observer.stop()
            self.observer.join(timeout=3)
            self.observer = None

    def due(self, last, now):
        # Avoid feedback loops on platforms that emit directory modifications.
        return now - last >= self.interval or (self.dirty.is_set() and now - last >= 2)


def snapshot_payload(root, snapshot, new):
    return {'root': str(root), 'files': snapshot.files, 'bytes': snapshot.bytes,
            'alerts': snapshot.alerts, 'new_alerts': sorted(new),
            'history': snapshot.history, 'warnings': snapshot.warnings, 'complete': snapshot.complete, 'skipped': snapshot.skipped, 'largest': snapshot.largest}


def run_watch(roots, interval=60, once=False, use_events=True, json_output=False,
              stop=None, emit=None, index=None, backup=False, quota_mib=256):
    """Run in the foreground (suitable for SSH, systemd, or a supervisor)."""
    stop = stop if stop is not None else threading.Event()
    index = index if index is not None else SafetyIndex()
    roots = list(dict.fromkeys(validated_root(root) for root in roots))
    if not roots:
        raise ValueError('Provide at least one folder.')
    if not 2 <= interval <= 86400:
        raise ValueError('Interval must be between 2 and 86400 seconds.')
    def output(payload):
        if emit is not None:
            emit(payload)
        elif json_output:
            print(json.dumps(payload, ensure_ascii=True), flush=True)
        elif 'error' in payload:
            print(f'{payload["root"]}: {payload["error"]}', file=sys.stderr, flush=True)
        else:
            status = f'{len(payload["alerts"])} broken links' if payload['complete'] else 'partial coverage; alerts unavailable'
            print(f'{payload["root"]}: {payload["files"]} files; {status}', flush=True)
            for source, target in payload['new_alerts']:
                print(f'  ALERT: {source} -> {target}', flush=True)
            for warning in payload['warnings']:
                print(f'  WARNING: {warning}', flush=True)
            if 'recovery' in payload:
                rec = payload['recovery']
                print(f'  Recovery: {rec["saved"]} saved, {rec["skipped"]} skipped; {rec["used"]}/{rec["quota"]} logical bytes', flush=True)
                for warning in rec['warnings'] or []:
                    print(f'  WARNING: {warning}', flush=True)
            if 'recovery_error' in payload:
                print(f'  Recovery error: {payload["recovery_error"]}', file=sys.stderr, flush=True)
    watches = {}
    last = {}
    previous = {}
    failed = False
    try:
        for root in roots:
            watches[root] = Wakeup(root, interval, use_events and not once)
            last[root] = float('-inf')
        while not stop.is_set():
            for root, wake in watches.items():
                if stop.is_set():
                    break
                if not wake.due(last[root], time.monotonic()):
                    continue
                wake.dirty.clear()
                try:
                    snapshot = index.refresh(root)
                    alerts = set(snapshot.alerts)
                    payload = snapshot_payload(root, snapshot, alerts - previous.get(root, set()) if snapshot.complete else set())
                    if backup and snapshot.complete:
                        try:
                            payload['recovery'] = asdict(RecoveryStore().capture(root, quota_mib * MIB))
                        except (OSError, ValueError, sqlite3.Error) as exc:
                            payload['recovery_error'] = str(exc)
                            failed = True
                    output(payload)
                    if snapshot.complete:
                        previous[root] = alerts
                    else:
                        failed = True
                except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                    output({'root': str(root), 'error': str(exc)})
                    failed = True
                last[root] = time.monotonic()
            if once:
                break
            stop.wait(0.5)
    finally:
        for wake in watches.values():
            wake.close()
    return int(failed) if once else 0


def add_commands(sub):
    watch = sub.add_parser('watch', help='Monitor folders without a GUI')
    watch.add_argument('folders', nargs='*', type=Path)
    watch.add_argument('--interval', type=int, default=60, help='Full reconciliation interval in seconds (2-86400)')
    watch.add_argument('--once', action='store_true', help='Take one snapshot and exit')
    watch.add_argument('--poll', action='store_true', help='Do not use optional OS file events')
    watch.add_argument('--json', action='store_true', help='Emit JSON lines')
    watch.add_argument('--backup', action='store_true', help='Opt in to saving local file versions')
    watch.add_argument('--quota-mib', type=int, choices=range(1,4097), metavar='1-4096', default=256)
    fleet = sub.add_parser('fleet-agent',help='Opt in to sending aggregate project reports to a self-hosted server')
    fleet.add_argument('folders',nargs='+',type=Path)
    fleet.add_argument('--server',required=True)
    fleet.add_argument('--id',required=True)
    fleet.add_argument('--interval',type=int,default=60)
    fleet.add_argument('--once',action='store_true')
    server = sub.add_parser('fleet-server',help='Run the authenticated fleet dashboard and collector')
    server.add_argument('--host',default='127.0.0.1')
    server.add_argument('--port',type=int,default=8765)
    server.add_argument('--db',type=Path,default=state_path().parent/'fleet.sqlite3')
    server.add_argument('--trusted-proxy',action='store_true',help='Allow non-loopback binding on a private reverse-proxy network only')
    protection = sub.add_parser('guard',help='Review or execute a guarded single-file operation')
    commands = protection.add_subparsers(dest='action',required=True)
    for action in ('preview','apply'):
        cmd=commands.add_parser(action)
        cmd.add_argument('root',type=Path)
        cmd.add_argument('source',type=Path)
        cmd.add_argument('--operation',choices=('move','rename','delete'),default='move')
        cmd.add_argument('--destination',type=Path)
        if action=='apply':
            cmd.add_argument('--confirm',required=True)
    commands.add_parser('rules')
    add=commands.add_parser('add-rule')
    add.add_argument('path',type=Path)
    add.add_argument('--mode',choices=('block','warn'),required=True)
    remove=commands.add_parser('remove-rule')
    remove.add_argument('path',type=Path)
    sub.add_parser('update-check',help='Check GitHub for a newer release (network request)')
    storage = sub.add_parser('storage', help='Analyze logical sizes without reading file contents')
    storage.add_argument('folder', type=Path)
    storage.add_argument('--max-entries', type=int, default=500000)
    storage.add_argument('--older-days', type=int, default=180)
    storage.add_argument('--min-mib', type=int, default=100)
    storage.add_argument('--json', action='store_true')
    repair = sub.add_parser('repair', help='Preview, apply or undo supported link repairs')
    repairs = repair.add_subparsers(dest='action', required=True)
    hint = repairs.add_parser('suggest')
    hint.add_argument('root', type=Path)
    for action in ('preview','apply'):
        cmd = repairs.add_parser(action)
        for name in ('root','source','old','new'):
            cmd.add_argument(name, type=Path)
        if action == 'apply':
            cmd.add_argument('--confirm', required=True, help='Exact token from preview')
    repairs.add_parser('history')
    undo = repairs.add_parser('undo')
    undo.add_argument('id', type=int)
    undo.add_argument('--yes', action='store_true', required=True)
    rec = sub.add_parser('recovery', help='Capture, list or restore saved file versions')
    actions = rec.add_subparsers(dest='action', required=True)
    capture = actions.add_parser('capture')
    capture.add_argument('folder', type=Path)
    capture.add_argument('--quota-mib', type=int, choices=range(1,4097), metavar='1-4096', default=256)
    listing = actions.add_parser('list')
    listing.add_argument('--folder', type=Path)
    listing.add_argument('--limit', type=int, default=1000)
    restore = actions.add_parser('restore')
    restore.add_argument('version', type=int)
    restore.add_argument('destination', type=Path)
    dup = sub.add_parser('duplicates', help='Find identical file contents without a GUI')
    dup.add_argument('folder', type=Path)
    dup.add_argument('--json', action='store_true')
    config = sub.add_parser('monitor-config', help='Show, set or clear the remembered monitor folder')
    group = config.add_mutually_exclusive_group()
    group.add_argument('--folder', type=Path)
    group.add_argument('--clear', action='store_true')


def dispatch(args):
    try:
        if args.command == 'monitor-config':
            prefs = read_preferences()
            if args.folder is not None:
                prefs.root = str(validated_root(args.folder))
                save_preferences(prefs)
            elif args.clear:
                prefs.root = ''
                save_preferences(prefs)
            print(json.dumps(asdict(prefs)))
            return 0
        if args.command == 'fleet-agent':
            from .fleet import agent_command
            return agent_command(args)
        if args.command == 'fleet-server':
            from .fleet_server import serve
            return serve(args)
        if args.command == 'update-check':
            from .updates import check_update
            print(json.dumps(check_update()))
            return 0
        if args.command == 'guard':
            from .guard import preview, apply, rules, set_rule, remove_rule
            if args.action=='add-rule':
                set_rule(args.path,args.mode)
            elif args.action=='remove-rule':
                remove_rule(args.path)
            elif args.action in ('preview','apply'):
                plan=preview(args.root,args.source,args.operation,args.destination)
                if args.action=='preview':
                    print(json.dumps(plan.as_dict(),indent=2))
                    return 0
                print(apply(plan,args.confirm))
                return 0
            print(json.dumps(rules(),indent=2))
            return 0
        if args.command == 'storage':
            from .storage import analyze_storage, human_size
            report = analyze_storage(args.folder, args.max_entries, args.older_days, args.min_mib*MIB)
            if args.json:
                print(json.dumps(report.as_dict(), indent=2))
            else:
                print(f'{report.root}: {report.files:,} files; {human_size(report.logical_bytes)} logical size')
                print('Complete observed scope' if report.complete else 'Partial coverage')
                for row in report.folders[:20]:
                    print(f'{human_size(row["bytes"]):>14}  {row["name"]}')
                print('Review candidates (not deletion recommendations):')
                for row in report.review[:20]:
                    print(f'{human_size(row["bytes"]):>14}  {row["modified_days_ago"]:>6} days  {row["path"]}')
                for warning in report.warnings:
                    print(f'WARNING: {warning}')
            return 0 if report.complete else 1
        if args.command == 'repair':
            from .repair import plan_repair, suggestions, RepairJournal
            journal = RepairJournal()
            if args.action == 'suggest':
                print(json.dumps(suggestions(args.root), indent=2))
            elif args.action == 'history':
                print(json.dumps(journal.entries(), indent=2))
            elif args.action == 'undo':
                print(journal.undo(args.id))
            else:
                plan = plan_repair(args.root,args.source,args.old,args.new)
                if args.action == 'preview':
                    print(json.dumps({'diff':plan.preview(),'replacements':plan.replacements,'confirm':plan.token},indent=2))
                else:
                    print(json.dumps({'repair_id':journal.apply(plan,args.confirm)}))
            return 0
        if args.command == 'recovery':
            store = RecoveryStore()
            if args.action == 'capture':
                result = store.capture(args.folder, args.quota_mib * MIB)
                print(json.dumps(asdict(result), indent=2))
            elif args.action == 'list':
                print(json.dumps(store.versions(args.folder, args.limit), indent=2))
            else:
                print(store.restore(args.version, args.destination))
            return 0
        if args.command == 'duplicates':
            groups, skipped, warnings, review = smart_duplicates(args.folder)
            payload = {'groups': [{'size': size, 'files': paths} for size, paths in groups],
                       'extra_logical_bytes': sum(size*(len(paths)-1) for size,paths in groups), 'skipped': skipped, 'warnings': warnings, 'review': review}
            if args.json:
                print(json.dumps(payload))
            else:
                print(f'{len(groups)} groups; {payload["extra_logical_bytes"]} additional logical bytes; {skipped} skipped')
                for row in review:
                    print(f'Group {row["group"]}: {row["path"]} | {row["size"]} bytes | {row["review"]}')
                for warning in warnings:
                    print(f'WARNING: {warning}')
            return 0
        roots = args.folders
        if not roots:
            saved = read_preferences().root
            roots = [saved] if saved else []
        stop = threading.Event()
        old = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            old[sig] = signal.signal(sig, lambda *_: stop.set())
        try:
            return run_watch(roots, args.interval, args.once, not args.poll, args.json, stop, backup=args.backup, quota_mib=args.quota_mib)
        finally:
            for sig, handler in old.items():
                signal.signal(sig, handler)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f'BreakCheck: {exc}', file=sys.stderr)
        return 1
