import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from breakcheck.guard import preview, apply, rules, set_rule, remove_rule, rename_no_replace
from breakcheck.updates import check_update, version
from breakcheck.agent import Preferences, read_preferences, save_preferences


class GuardTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base=Path(temp.name).resolve()
        self.root=base/'project'
        self.root.mkdir()
        env=patch.dict(os.environ,{'BREAKCHECK_STATE_DIR':str(base/'state')})
        env.start()
        self.addCleanup(env.stop)
        self.source=self.root/'asset.png'
        self.source.write_bytes(b'file contents')
        (self.root/'index.html').write_text('<img src="asset.png">',encoding='utf-8')

    def plan(self):
        return preview(self.root,'asset.png','rename','new.png')

    def test_review_and_rules(self):
        set_rule(self.root,'warn')
        plan=self.plan()
        self.assertEqual(len(plan.evidence['direct']),1)
        self.assertEqual(plan.evidence['rules'][0]['mode'],'warn')
        set_rule(self.source,'block')
        self.assertTrue(self.plan().evidence['blocked'])
        self.assertFalse(self.plan().evidence['executable'])
        with self.assertRaises(ValueError):
            blocked=self.plan()
            apply(blocked,blocked.token)
        remove_rule(self.source)
        self.assertEqual(len(rules()),1)
        self.assertTrue(self.source.exists())

    def test_destination_rule_and_delete_review(self):
        folder=self.root/'protected'
        folder.mkdir()
        set_rule(folder,'block')
        plan=preview(self.root,'asset.png','move','protected/new.png')
        self.assertTrue(plan.evidence['blocked'])
        delete=preview(self.root,'asset.png','delete')
        self.assertFalse(delete.evidence['executable'])
        with self.assertRaises(ValueError):
            apply(delete,delete.token)
        self.assertTrue(self.source.exists())

    def test_changed_rules_or_source_invalidate_preview(self):
        plan=self.plan()
        set_rule(self.root,'warn')
        with self.assertRaises(ValueError):
            apply(plan,plan.token)
        plan=self.plan()
        self.source.write_bytes(b'new contents')
        with self.assertRaises(ValueError):
            apply(plan,plan.token)

    @unittest.skipUnless(sys.platform.startswith(('win','linux')),'Windows/Linux only')
    def test_actual_move_and_no_overwrite(self):
        plan=self.plan()
        self.assertTrue(plan.evidence['executable'])
        dest=apply(plan,plan.token)
        self.assertEqual(dest.read_bytes(),b'file contents')
        self.assertFalse(self.source.exists())
        self.source.write_bytes(b'other')
        with self.assertRaises(OSError):
            rename_no_replace(self.source,dest)
        self.assertEqual(dest.read_bytes(),b'file contents')
        self.assertEqual(self.source.read_bytes(),b'other')

    def test_scope_and_existing_destination(self):
        with self.assertRaises(ValueError):
            preview(self.root,'asset.png','move','../outside.png')
        with self.assertRaises(ValueError):
            preview(self.root,'asset.png','move','index.html')

    def test_updates_and_opt_in_preferences(self):
        self.assertFalse(read_preferences().auto_updates)
        save_preferences(Preferences(auto_updates=True))
        self.assertTrue(read_preferences().auto_updates)
        with patch('breakcheck.updates.urlopen',return_value=io.BytesIO(json.dumps({'tag_name':'v99.0.0'}).encode())) as mock:
            result=check_update()
        self.assertTrue(result['available'])
        self.assertEqual(mock.call_args.kwargs['timeout'],8)
        self.assertGreater(version('v1.10.0'),version('1.9.0'))
