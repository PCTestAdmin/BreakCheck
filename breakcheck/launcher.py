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


def run_desktop(inspect=None, root=None, self_test=False):
    from .gui import App
    from .core import scan, analyze
    app = App(self_test=self_test)
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
                app.safety.render_duplicates(folder, duplicates(folder))
                app.update_idletasks()
                if len(app.safety.alerts.get_children()) != 1 or len(app.safety.dupes.get_children()) != 2:
                    raise RuntimeError('Safety Center self-test failed.')
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
    app.mainloop()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='BreakCheck desktop application')
    parser.add_argument('--inspect', help='Preselect a file or folder')
    parser.add_argument('--root', help='Initial scan folder')
    parser.add_argument('--self-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    return run_desktop(args.inspect, args.root, args.self_test)
