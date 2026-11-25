import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from breakcheck.recovery import RecoveryStore
from breakcheck.smart import smart_duplicates


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        env = patch.dict(os.environ, {'BREAKCHECK_STATE_DIR': str(self.base / 'state')})
        env.start()
        self.addCleanup(env.stop)
        self.store = RecoveryStore()

    def test_versions_survive_delete_and_restore(self):
        path = self.root / 'file.txt'
        path.write_bytes(b'first')
        self.assertEqual(self.store.capture(self.root).saved, 1)
        self.assertEqual(self.store.capture(self.root).saved, 0)
        path.write_bytes(b'second version')
        self.assertEqual(self.store.capture(self.root).saved, 1)
        path.unlink()
        versions = self.store.versions()
        self.assertEqual(len(versions), 2)
        self.store.restore(versions[1]['id'], path)
        self.assertEqual(path.read_bytes(), b'first')
        with self.assertRaises(FileExistsError):
            self.store.restore(versions[0]['id'], path)
        self.assertEqual(path.read_bytes(), b'first')

    def test_quota_preserves_old_versions(self):
        path = self.root / 'file.txt'
        path.write_bytes(b'1234')
        self.assertEqual(self.store.capture(self.root, quota=4).saved, 1)
        path.write_bytes(b'abcdef')
        result = self.store.capture(self.root, quota=4)
        self.assertEqual(result.saved, 0)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.used, 4)
        self.assertEqual(len(self.store.versions()), 1)

    def test_restore_race_cannot_overwrite(self):
        (self.root / 'file.txt').write_bytes(b'original')
        self.store.capture(self.root)
        version = self.store.versions()[0]['id']
        output = self.root / 'restored.txt'
        link = os.link
        def competing_file(source, destination):
            Path(destination).write_bytes(b'other writer')
            return link(source, destination)
        with patch('breakcheck.recovery.os.link', side_effect=competing_file):
            with self.assertRaises(FileExistsError):
                self.store.restore(version, output)
        self.assertEqual(output.read_bytes(), b'other writer')
        self.assertFalse(list(self.root.glob('.breakcheck-restore-*')))

    def test_corrupted_version_refused(self):
        from contextlib import closing
        path = self.root / 'file.txt'
        path.write_bytes(b'abc')
        self.store.capture(self.root)
        version = self.store.versions()[0]['id']
        with closing(self.store.connect()) as db, db:
            db.execute('UPDATE versions SET data=? WHERE id=?', (b'xyz',version))
        output = self.root / 'restored.txt'
        with self.assertRaises(ValueError):
            self.store.restore(version, output)
        self.assertFalse(output.exists())

    def test_oversize_and_private_data(self):
        with patch('breakcheck.recovery.MAX_FILE', 2):
            (self.root / 'file.txt').write_bytes(b'abc')
            self.assertEqual(self.store.capture(self.root).skipped, 1)
        with self.assertRaises(ValueError):
            self.store.capture(self.base)

    def test_duplicate_reference_review(self):
        (self.root / 'a.png').write_bytes(b'copy')
        (self.root / 'b.png').write_bytes(b'copy')
        (self.root / 'index.html').write_text('<img src="a.png">', encoding='utf-8')
        groups, skipped, warnings, review = smart_duplicates(self.root)
        self.assertEqual(len(groups), 1)
        self.assertEqual([(r['path'],r['references']) for r in review], [('a.png',1),('b.png',0)])
        self.assertIn('Keep', review[0]['review'])
        self.assertIn('Review', review[1]['review'])
