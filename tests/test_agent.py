"""Headless monitoring tests require neither Tk nor optional dependencies."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from breakcheck.agent import Preferences, read_preferences, save_preferences, Wakeup, run_watch
from breakcheck.safety import SafetyIndex


class AgentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.project = self.base / 'project'
        self.project.mkdir()
        self.state = self.base / 'state'
        env = patch.dict(os.environ, {'BREAKCHECK_STATE_DIR': str(self.state)})
        env.start()
        self.addCleanup(env.stop)

    def test_preferences_round_trip(self):
        self.assertEqual(read_preferences(), Preferences())
        prefs = Preferences(str(self.project), False)
        save_preferences(prefs)
        self.assertEqual(read_preferences(), prefs)
        save_preferences(Preferences())
        self.assertEqual(read_preferences(), Preferences())

    def test_headless_snapshot_and_alert(self):
        target = self.project / 'asset.png'
        target.write_bytes(b'asset')
        (self.project / 'index.html').write_text('<img src="asset.png">', encoding='utf-8')
        records = []
        self.assertEqual(run_watch([self.project], once=True, emit=records.append), 0)
        self.assertEqual(records[-1]['alerts'], [])
        target.unlink()
        self.assertEqual(run_watch([self.project], once=True, emit=records.append), 0)
        self.assertEqual(records[-1]['new_alerts'], [('index.html','asset.png')])

    def test_multiple_roots_and_error_status(self):
        other = self.base / 'other'
        other.mkdir()
        records = []
        self.assertEqual(run_watch([self.project,other,self.project], once=True, emit=records.append), 0)
        self.assertEqual(len(records), 2)
        with patch.object(SafetyIndex, 'refresh', side_effect=OSError('denied')):
            self.assertEqual(run_watch([other], once=True, emit=records.append), 1)
        self.assertIn('denied', records[-1]['error'])

    def test_events_debounce_and_reconcile(self):
        wake = Wakeup(self.project, interval=60, use_events=False)
        try:
            wake.mark('opened', self.project / 'file')
            wake.mark('modified', self.project / '.git' / 'index')
            wake.mark('created', self.base / 'outside')
            self.assertFalse(wake.dirty.is_set())
            self.assertFalse(wake.due(10, 20))
            self.assertTrue(wake.due(10, 70))
            wake.mark('created', self.project / 'file')
            self.assertFalse(wake.due(10, 11))
            self.assertTrue(wake.due(10, 12))
        finally:
            wake.close()

    def test_reject_state_directory(self):
        with self.assertRaises(ValueError):
            run_watch([self.base], once=True)
