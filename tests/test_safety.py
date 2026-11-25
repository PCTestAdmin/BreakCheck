import os
import sqlite3
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from breakcheck.safety import SafetyIndex, duplicates


class SafetyTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base = Path(t.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        self.db = self.base / 'state' / 'index.sqlite3'
        self.index = SafetyIndex(self.db)

    def write(self, p, data):
        path = self.root / p
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_persistent_change_and_broken_link(self):
        target = self.write('asset.png', b'demo')
        self.write('index.html', b'<img src="asset.png">')
        baseline = self.index.refresh(self.root)
        self.assertFalse(baseline.history)
        target.rename(self.root / 'moved.png')
        second = SafetyIndex(self.db).refresh(self.root)
        self.assertEqual(second.alerts, [('index.html', 'asset.png')])
        self.assertIn(('Possible move','asset.png','moved.png'), [e[1:] for e in second.history])
        self.assertEqual(self.index.refresh(self.root).alerts, second.alerts)
        self.write('index.html', b'<img src="moved.png">')
        self.assertFalse(self.index.refresh(self.root).alerts)

    def test_restore_path_clears_alert(self):
        target = self.write('asset.png', b'demo')
        self.write('index.html', b'<img src="asset.png">')
        self.index.refresh(self.root)
        target.unlink()
        self.assertTrue(self.index.refresh(self.root).alerts)
        self.write('asset.png', b'demo')
        self.assertFalse(self.index.refresh(self.root).alerts)

    def test_modified_and_added(self):
        self.write('x.txt', b'old')
        self.index.refresh(self.root)
        self.write('x.txt', b'new data')
        self.write('new.txt', b'new')
        events = [e[1:3] for e in self.index.refresh(self.root).history]
        self.assertIn(('Changed','x.txt'), events)
        self.assertIn(('Added','new.txt'), events)

    def test_incomplete_scan_preserves_snapshot(self):
        target = self.write('asset.png', b'demo')
        self.index.refresh(self.root)
        with patch('breakcheck.safety.inventory', side_effect=OSError('denied')):
            with self.assertRaises(OSError):
                self.index.refresh(self.root)
        target.unlink()
        self.assertIn(('Removed','asset.png'), [e[1:3] for e in self.index.refresh(self.root).history])

    def test_permission_skip_preserves_baseline(self):
        from breakcheck.safety import inventory
        target = self.write('private/asset.png', b'demo')
        self.write('index.html', b'<img src="private/asset.png">')
        self.index.refresh(self.root)
        original = os.walk
        def denied(root, *args, **kwargs):
            if Path(root) != self.root:
                yield from original(root, *args, **kwargs)
                return
            yield str(self.root), ['private'], ['index.html']
            kwargs['onerror'](PermissionError(13, 'Access denied', str(self.root / 'private')))
        with patch('breakcheck.safety.os.walk', side_effect=denied):
            result = self.index.refresh(self.root)
            self.assertFalse(result.complete)
            self.assertEqual(result.alerts, [])
            self.assertEqual(result.history, [])
            self.assertTrue(any('Access skipped' in w for w in result.warnings))
        target.unlink()
        self.assertEqual(self.index.refresh(self.root).alerts, [('index.html','private/asset.png')])

    def test_file_limit_returns_partial_inventory(self):
        from breakcheck.safety import inventory
        self.write('a.bin', b'a')
        self.write('b.bin', b'b')
        result = inventory(self.root, max_files=1)
        self.assertFalse(result.complete)
        self.assertEqual(len(result), 1)
        self.assertTrue(result.warnings)

    def test_preview_largest_files_without_creating_database(self):
        from breakcheck.safety import preview
        self.write('small.txt', b'a')
        self.write('big.txt', b'abcdef')
        result = preview(self.root, self.db)
        self.assertFalse(result.complete)
        self.assertEqual(result.largest, [('big.txt', 6), ('small.txt', 1)])
        self.assertFalse(self.db.exists())

    def test_missing_target_access_denied_is_not_deletion(self):
        from breakcheck.safety import missing_target
        with patch.object(Path, 'lstat', side_effect=PermissionError('denied')):
            self.assertFalse(missing_target(self.root / 'private'))
        self.assertTrue(missing_target(self.root / 'missing'))

    def test_duplicate_content_not_name_or_size(self):
        self.write('a/one.bin', b'abcd')
        self.write('b/two.bin', b'abcd')
        self.write('c/one.bin', b'wxyz')
        self.assertEqual(duplicates(self.root), ([(4,['a/one.bin','b/two.bin'])],0))
        groups, skipped = duplicates(self.root,budget=4)
        self.assertFalse(groups)
        self.assertEqual(skipped,2)

    def test_hardlinks_not_counted(self):
        target = self.write('one.bin', b'abcd')
        try:
            os.link(target,self.root / 'linked.bin')
        except OSError:
            self.skipTest('Hard links unavailable')
        self.assertEqual(duplicates(self.root), ([],0))

    def test_large_device_id_round_trip_with_legacy_schema(self):
        self.write('asset.png', b'demo')
        self.write('index.html', b'<img src="asset.png">')
        self.index.refresh(self.root)
        # Recreate the v0.4.0 INTEGER-affinity column, with valid legacy rows.
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('ALTER TABLE files RENAME TO old_files')
            db.execute('CREATE TABLE files (root TEXT, path TEXT, size INTEGER, mtime INTEGER, dev INTEGER, ino TEXT, links INTEGER, PRIMARY KEY(root,path))')
            db.execute('INSERT INTO files SELECT root,path,size,mtime,42,ino,links FROM old_files')
            db.execute('DROP TABLE old_files')
        from breakcheck.safety import inventory
        real = inventory(self.root)
        large = (1 << 64) - 59
        simulated = {p: (s,m,large,i,n) for p,(s,m,d,i,n) in real.items()}
        with patch('breakcheck.safety.inventory', return_value=simulated):
            self.index.refresh(self.root)
            second = self.index.refresh(self.root)
            # No duplicate change events on the second scan: identity is exact.
            self.assertEqual(len(second.history), len(real))
            with closing(sqlite3.connect(self.db)) as db, db:
                values = db.execute('SELECT dev,typeof(dev) FROM files').fetchall()
                self.assertEqual(values, [(f'd:{large}', 'text')] * len(real))
            self.assertFalse(second.alerts)

    def test_database_must_be_outside_folder(self):
        with self.assertRaises(ValueError):
            SafetyIndex(self.root / 'db.sqlite3').refresh(self.root)
        overview = SafetyIndex(self.root / 'state' / 'db.sqlite3').refresh(self.root)
        self.assertFalse(overview.complete)
        self.assertFalse((self.root / 'state' / 'db.sqlite3').exists())
