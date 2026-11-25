import errno
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from breakcheck.agent import Preferences,read_preferences,save_preferences,Wakeup
from breakcheck.brand import icon_png
from breakcheck.desktop import explain_error

class DesktopTests(unittest.TestCase):
    def test_legacy_preferences_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'preferences.json'
            path.write_text(json.dumps({'root':'project','notifications':False}),encoding='utf-8')
            old=read_preferences(path)
            self.assertTrue(old.dark)
            self.assertFalse(old.welcome_seen)
            self.assertEqual(old.desktop_interval,60)
            prefs=Preferences(root='project',notifications=False,dark=False,welcome_seen=True,desktop_interval=120,desktop_events=False)
            save_preferences(prefs,path)
            self.assertEqual(read_preferences(path),prefs)

    def test_reject_invalid_desktop_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'preferences.json'
            for data in ({'desktop_interval':0},{'desktop_interval':True},{'dark':'false'},{'desktop_events':0}):
                path.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_preferences(path)

    def test_desktop_event_coalescing(self):
        wake=Wakeup(Path.cwd(),interval=60,use_events=False,event_gap=10)
        wake.dirty.set()
        self.assertFalse(wake.due(100,109))
        self.assertTrue(wake.due(100,110))
        wake.dirty.clear()
        self.assertFalse(wake.due(100,159))
        self.assertTrue(wake.due(100,160))
        wake.close()

    def test_icon_dimensions(self):
        for size in (16,32,64,256):
            data=icon_png(size)
            self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II',data[16:24]),(size,size))
        with self.assertRaises(ValueError):
            icon_png(0)

    def test_explain_errors(self):
        self.assertIn('protected',explain_error(PermissionError('denied')))
        self.assertIn('missing',explain_error(FileNotFoundError('missing path')))
        self.assertIn('free space',explain_error(OSError(errno.ENOSPC,'full')))
        self.assertEqual(explain_error(ValueError('invalid')),'invalid')
