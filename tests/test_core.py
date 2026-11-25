import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from breakcheck.core import scan, analyze, MAX_BYTES
from breakcheck.__main__ import main


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.logo = self.write('assets/logo.png', 'image placeholder')

    def write(self, name, content):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p

    def test_html_css_markdown_json_and_indirect(self):
        self.write('site/index.html', '<img src="../assets/logo.png?x=1#top"><link href="style.css">')
        self.write('site/style.css', 'body {background: url(../assets/logo.png)}')
        self.write('README.md', '[Page](site/index.html)')
        self.write('config.json', json.dumps({'logo': 'assets/logo.png'}))
        r = analyze(scan(self.root), self.logo)
        self.assertEqual({i.reference.source.name for i in r.direct}, {'index.html', 'style.css', 'config.json'})
        self.assertEqual([p.name for p in r.indirect], ['README.md'])
        self.assertTrue(self.logo.exists())

    def test_folder_delete_ignores_internal_dependents(self):
        self.write('assets/index.html', '<img src="logo.png">')
        self.write('external.md', '![Image](assets/logo.png)')
        r = analyze(scan(self.root), self.logo.parent)
        self.assertEqual([i.reference.source.name for i in r.direct], ['external.md'])

    def test_folder_move_preserves_internal_relative_paths(self):
        self.write('assets/index.html', '<img src="logo.png">')
        self.write('external.md', '![Image](assets/logo.png)')
        r = analyze(scan(self.root), self.logo.parent, 'move', self.root / 'new-assets')
        self.assertEqual([i.reference.source.name for i in r.direct], ['external.md'])

    def test_moving_source_breaks_outgoing_relative_link(self):
        source = self.write('index.html', '<img src="assets/logo.png">')
        r = analyze(scan(self.root), source, 'move', self.root / 'sub/index.html')
        self.assertEqual(len(r.direct), 1)
        self.assertTrue(source.exists())

    def test_rename_and_encoded_spaces(self):
        target = self.write('assets/my icon.png', 'dummy')
        self.write('index.html', '<img src="assets/my%20icon.png">')
        r = analyze(scan(self.root), target, 'rename', target.with_name('new.png'))
        self.assertEqual(len(r.direct), 1)

    def test_office_external_relationship(self):
        for suffix in ('xlsx', 'docx', 'pptx'):
            with zipfile.ZipFile(self.root / f'book.{suffix}', 'w') as z:
                z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="assets/logo.png" TargetMode="External"/></Relationships>')
        self.assertEqual(len(analyze(scan(self.root), self.logo).direct), 3)

    def test_unsupported_and_bad_data_reported(self):
        self.write('broken.json', '{')
        self.write('scene.blend', 'not supported')
        self.write('base.html', '<base href="/other/"><img src="assets/logo.png">')
        s = scan(self.root)
        self.assertEqual(s.unsupported, 2)
        self.assertEqual(s.skipped, 1)
        self.assertEqual(len(s.warnings), 2)
        self.assertFalse(s.references)

    def test_remote_links_and_missing_paths_ignored(self):
        self.write('index.html', '<img src="https://example.org/logo.png"><img src="missing.png"><img src="/assets/logo.png">')
        self.assertFalse(scan(self.root).references)

    def test_file_uri_absolute_reference(self):
        self.write('assets/index.html', f'<img src="{self.logo.as_uri()}">')
        r = analyze(scan(self.root), self.logo.parent, 'move', self.root / 'other')
        self.assertEqual(len(r.direct), 1)

    def test_limits(self):
        self.write('large.md', 'x' * (MAX_BYTES + 1))
        s = scan(self.root)
        self.assertTrue(any('scan limit' in w for w in s.warnings))
        self.assertTrue(scan(self.root, max_files=1).warnings)

    def test_cycles(self):
        self.write('a.md', '[B](b.md) ![Logo](assets/logo.png)')
        self.write('b.md', '[A](a.md)')
        r = analyze(scan(self.root), self.logo)
        self.assertEqual([p.name for p in r.indirect], ['b.md'])

    def test_invalid_destination(self):
        s = scan(self.root)
        with self.assertRaises(ValueError):
            analyze(s, self.logo, 'rename', self.root / 'elsewhere.png')
        with self.assertRaises(ValueError):
            analyze(s, self.logo, 'move', self.logo.parent)
        with self.assertRaises(ValueError):
            analyze(s, self.root.parent)

    def test_cli_json_and_exit_codes(self):
        self.write('index.html', '<img src="assets/logo.png">')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['check', str(self.root), 'assets/logo.png', '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(len(json.loads(out.getvalue())['direct']), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['check', str(self.root), 'index.html']), 0)


if __name__ == '__main__':
    unittest.main()
