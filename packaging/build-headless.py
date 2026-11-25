"""Build the portable, dependency-free Python zip application."""
from pathlib import Path
import shutil
import tempfile
import zipapp

root = Path(__file__).resolve().parent.parent
output = root / 'release' / 'BreakCheck.pyz'
output.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    stage = Path(folder)
    shutil.copytree(root / 'breakcheck', stage / 'breakcheck',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (stage / '__main__.py').write_text('from breakcheck.__main__ import main\nraise SystemExit(main())\n', encoding='utf-8')
    shutil.copy2(root / 'LICENSE', stage / 'LICENSE')
    zipapp.create_archive(stage, output, interpreter='/usr/bin/env python3', compressed=True)
print(output)
