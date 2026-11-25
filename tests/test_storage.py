import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from breakcheck.storage import analyze_storage, DAY


class StorageTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base=Path(temp.name).resolve()
        self.root=base/'project'
        self.root.mkdir()
        env=patch.dict(os.environ,{'BREAKCHECK_STATE_DIR':str(base/'state')})
        env.start()
        self.addCleanup(env.stop)

    def write(self,name,size,days):
        path=self.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'x'*size)
        os.utime(path,(1700000000-days*DAY,)*2)
        return path

    def test_totals_categories_and_age(self):
        self.write('media/movie.mp4',8,400)
        self.write('notes.txt',4,10)
        self.write('media/photo.png',2,45)
        report=analyze_storage(self.root,older_days=180,min_bytes=1,now=1700000000)
        self.assertTrue(report.complete)
        self.assertEqual((report.files,report.logical_bytes),(3,14))
        self.assertEqual(report.folders[0],{'name':'media','directory':True,'bytes':10,'files':2})
        self.assertEqual(sum(r['bytes'] for r in report.categories),14)
        self.assertEqual(sum(r['bytes'] for r in report.ages),14)
        self.assertEqual([r['path'] for r in report.review],['media/movie.mp4'])
        self.assertEqual(report.largest[0]['bytes'],8)

    def test_entry_limit_counts_directories(self):
        for i in range(5):
            (self.root/str(i)).mkdir()
        report=analyze_storage(self.root,max_entries=2)
        self.assertFalse(report.complete)
        self.assertEqual(report.entries,2)

    def test_cancel(self):
        stop=threading.Event()
        stop.set()
        report=analyze_storage(self.root,stop=stop)
        self.assertTrue(report.cancelled)
        self.assertFalse(report.complete)

    def test_excluded_state_and_symlinks(self):
        self.write('visible.txt',3,10)
        private=self.root/'private'
        private.mkdir()
        (private/'hidden.txt').write_bytes(b'hidden')
        with patch.dict(os.environ,{'BREAKCHECK_STATE_DIR':str(private)}):
            report=analyze_storage(self.root)
        self.assertEqual(report.logical_bytes,3)
        self.assertFalse(report.complete)
        self.assertTrue(report.warnings)

    def test_hard_links_are_logical_bytes(self):
        path=self.write('original.txt',4,10)
        try:
            os.link(path,self.root/'copy.txt')
        except OSError:
            self.skipTest('Hard links unavailable')
        report=analyze_storage(self.root)
        self.assertEqual(report.logical_bytes,8)
        self.assertTrue(all(row['hard_links']>=2 for row in report.largest))

    def test_no_content_reads(self):
        self.write('data.bin',5,10)
        with patch.object(Path,'open',side_effect=AssertionError('No content reads allowed')):
            self.assertEqual(analyze_storage(self.root).logical_bytes,5)
