"""Packaged GUI entry point with a noninteractive CI self-test."""
import os
import sys
import traceback
from pathlib import Path


def entry():
    # A windowed PyInstaller executable has no console. Catch self-test
    # failures explicitly so the bootloader never opens an error dialog.
    if '--self-test' not in sys.argv[1:]:
        from breakcheck.launcher import main
        return main()
    log = os.environ.get('BREAKCHECK_SELF_TEST_LOG')
    try:
        from breakcheck.launcher import main
        code = main()
        if code != 0:
            raise RuntimeError(f'Desktop self-test returned {code}')
        if log:
            Path(log).write_text('PASS\n', encoding='utf-8')
        return 0
    except BaseException:
        if log:
            try:
                Path(log).write_text(traceback.format_exc(), encoding='utf-8')
            except OSError:
                pass
        return 1


if __name__ == '__main__':
    raise SystemExit(entry())
