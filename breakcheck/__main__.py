"""BreakCheck command-line entry point."""
import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .core import scan, analyze


def main(argv=None):
    parser = argparse.ArgumentParser(description='Know what breaks before you break it. Read-only simulation.')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command')
    gui = sub.add_parser('gui', help='Open desktop interface')
    gui.add_argument('--inspect', help='Preselect a file or folder')
    gui.add_argument('--root', help='Initial scan folder')
    check = sub.add_parser('check', help='Scan and simulate a change')
    check.add_argument('root', type=Path)
    check.add_argument('target', type=Path, help='Target path, relative to root or absolute')
    check.add_argument('--operation', choices=['delete', 'move', 'rename'], default='delete')
    check.add_argument('--destination', type=Path, help='New path, relative to root or absolute')
    check.add_argument('--max-files', type=int, default=100000)
    check.add_argument('--json', action='store_true', help='Emit machine-readable JSON')
    inventory = sub.add_parser('inventory', help='List media assets with no detected incoming references')
    inventory.add_argument('root', type=Path)
    inventory.add_argument('--max-files', type=int, default=100000)
    inventory.add_argument('--json', action='store_true')
    gui.add_argument('--background', action='store_true', help='Start in the Windows notification area')
    from .agent import add_commands, dispatch
    add_commands(sub)
    args = parser.parse_args(argv)
    if args.command in ('watch', 'monitor-config', 'duplicates', 'recovery', 'repair'):
        return dispatch(args)
    if args.command in (None, 'gui'):
        try:
            from .launcher import run_desktop
            return run_desktop(getattr(args, 'inspect', None), getattr(args, 'root', None), background=getattr(args, 'background', False))
        except Exception as exc:
            print(f'Unable to launch desktop interface: {exc}', file=sys.stderr)
            return 1
        return 0
    try:
        index = scan(args.root, args.max_files)
        if args.command == 'inventory':
            from .insights import candidates, NOTICE
            rows = candidates(index)
            if args.json:
                print(json.dumps({'notice': NOTICE, 'root': str(index.root), 'candidates': [{'path': str(p), 'bytes': size} for p, size in rows], 'coverage': {'files_seen': index.files_seen, 'files_parsed': index.files_parsed, 'unsupported': index.unsupported, 'skipped': index.skipped, 'warnings': index.warnings}}, indent=2))
            else:
                print(NOTICE)
                for path, size in rows:
                    print(f'{size:>12,} bytes  {path}')
                print(f'{len(rows)} candidates; {index.unsupported} unsupported files; {index.skipped} skipped entries')
                for warning in index.warnings:
                    print(f'Warning: {warning}')
            return 0
        report = analyze(index, index.root / args.target, args.operation,
                         index.root / args.destination if args.destination else None)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(f'BreakCheck | {report.operation.upper()} {report.target}')
        print(f'{len(report.direct)} direct reference(s), {len(report.indirect)} potential indirect dependent(s)')
        for impact in report.direct:
            r = impact.reference
            print(f'  {r.source}{":" + str(r.line) if r.line else ""} -> {r.target} [{r.kind}]')
            print(f'    {impact.reason}')
        for source in report.indirect:
            print(f'  Indirect: {source}')
        print(f'Coverage: {index.files_parsed}/{index.files_seen} files parsed; {index.unsupported} unsupported; {index.skipped} skipped entries')
        for warning in index.warnings:
            print(f'  Warning: {warning}')
        print('No changes made. No detected references does not prove safety.')
    return 2 if report.direct else 0


if __name__ == '__main__':
    sys.exit(main())
