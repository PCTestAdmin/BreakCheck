import tempfile
import unittest
from pathlib import Path
from breakcheck.launcher import launch_paths


class LaunchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.folder = self.root / 'Project with spaces'
        self.folder.mkdir()
        self.target = self.folder / 'logo.png'
        self.target.write_bytes(b'demo')

    def test_empty(self):
        self.assertEqual(launch_paths(), (None, None))

    def test_file(self):
        self.assertEqual(launch_paths(self.target), (self.folder, self.target))

    def test_directory(self):
        self.assertEqual(launch_paths(self.folder), (self.root, self.folder))

    def test_wider_scope(self):
        self.assertEqual(launch_paths(self.target, self.root), (self.root, self.target))

    def test_missing_target(self):
        with self.assertRaises(ValueError):
            launch_paths(self.root / 'missing')

    def test_outside_scope(self):
        other = self.root / 'other'
        other.mkdir()
        with self.assertRaises(ValueError):
            launch_paths(self.target, other)
