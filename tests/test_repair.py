from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from breakcheck.repair import plan_repair, RepairJournal, suggestions
from breakcheck.safety import SafetyIndex


class RepairTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.root = base / 'project'
        self.root.mkdir()
        env = patch.dict(os.environ, {'BREAKCHECK_STATE_DIR': str(base / 'state')})
        env.start()
        self.addCleanup(env.stop)
        self.journal = RepairJournal()
        (self.root / 'new file.png').write_bytes(b'image')

    def plan(self, name='index.html', old='old.png', new='new file.png'):
        return plan_repair(self.root,name,old,new)

    def test_html_preserves_unrelated_text_and_bytes(self):
        source = self.root / 'index.html'
        original = b'\xef\xbb\xbf<!-- <img src="old.png"> -->\r\n<div title=\'src="old.png"\'><img SRC="old.png?x=1#top"></div>\r\n'
        source.write_bytes(original)
        plan = self.plan()
        self.assertEqual(plan.replacements, 1)
        self.assertEqual(plan.after, original.replace(b'SRC="old.png?',b'SRC="new%20file.png?'))
        self.assertEqual(source.read_bytes(),original)
        ident = self.journal.apply(plan,plan.token)
        self.assertEqual(source.read_bytes(),plan.after)
        self.journal.undo(ident)
        self.assertEqual(source.read_bytes(),original)

    def test_json_values_only(self):
        source = self.root / 'config.json'
        source.write_text('{"old.png": "old.png", "description": "not old.png", "list": ["old.png"]}',encoding='utf-8')
        plan = self.plan('config.json')
        self.assertEqual(plan.replacements,2)
        self.assertEqual(plan.after.decode(),'{"old.png": "new file.png", "description": "not old.png", "list": ["new file.png"]}')

    def test_stale_preview_rejected(self):
        source = self.root / 'index.html'
        source.write_bytes(b'<img src="old.png">')
        plan = self.plan()
        changed = b'<img src="old.png"> revised'
        source.write_bytes(changed)
        with self.assertRaises(ValueError):
            self.journal.apply(plan,plan.token)
        self.assertEqual(source.read_bytes(),changed)
        self.assertEqual(self.journal.entries(),[])

    def test_undo_refuses_external_edit(self):
        source = self.root / 'index.html'
        source.write_bytes(b'<img src="old.png">')
        plan = self.plan()
        ident = self.journal.apply(plan,plan.token)
        source.write_bytes(plan.after+b'edited')
        with self.assertRaises(ValueError):
            self.journal.undo(ident)
        self.assertEqual(source.read_bytes(),plan.after+b'edited')

    def test_reject_unsupported_and_outside(self):
        source = self.root / 'index.html'
        source.write_bytes(b'<base href="sub/"><img src="old.png">')
        with self.assertRaises(ValueError):
            self.plan()
        with self.assertRaises(ValueError):
            self.plan(old='../outside.png')
        (self.root / 'style.css').write_bytes(b'url(old.png)')
        with self.assertRaises(ValueError):
            self.plan('style.css')
        (self.root / 'old.png').write_bytes(b'present')
        with self.assertRaises(ValueError):
            self.plan()

    def test_move_suggestion(self):
        source = self.root / 'index.html'
        source.write_bytes(b'<img src="old.png">')
        old = self.root / 'old.png'
        old.write_bytes(b'original')
        index = SafetyIndex()
        index.refresh(self.root)
        old.rename(self.root / 'moved.png')
        index.refresh(self.root)
        self.assertEqual(suggestions(self.root),[{'source':'index.html','old':'old.png','new':'moved.png','replacements':1}])

    def test_confirmation_token_and_full_journal(self):
        source = self.root / 'index.html'
        source.write_bytes(b'<img src="old.png">')
        plan = self.plan()
        with self.assertRaises(ValueError):
            self.journal.apply(plan,'wrong')
        with patch('breakcheck.repair.MAX_ENTRIES',0):
            with self.assertRaises(ValueError):
                self.journal.apply(plan,plan.token)
        self.assertEqual(source.read_bytes(),plan.before)
