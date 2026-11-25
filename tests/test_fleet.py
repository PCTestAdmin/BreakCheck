import base64
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from breakcheck.fleet import collect, send, validate_report, endpoint, COUNTERS
from breakcheck.fleet_server import make_server, FleetStore, credentials
from breakcheck.safety import Snapshot


class FleetTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve()
        self.admin='A'*43
        self.token='B'*43
        self.other='C'*43
        self.keys={'office-01':self.token,'office-02':self.other}
        self.db=self.base/'fleet.sqlite3'
        self.data=dict.fromkeys(COUNTERS,0)
        self.data.update(version='1.1.0',interval=60,folders=1,files=3,logical_bytes=18)
        self.server=make_server('127.0.0.1',0,self.db,self.admin,self.keys)
        self.addCleanup(self.server.server_close)
        thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
        thread.start()
        self.addCleanup(thread.join,3)
        self.addCleanup(self.server.shutdown)
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def request(self,path,token=None,data=None,basic=False):
        headers={}
        if token:
            headers['Authorization']='Basic '+base64.b64encode(('admin:'+token).encode()).decode() if basic else 'Bearer '+token
        if data is not None:
            headers['Content-Type']='application/json'
        with urlopen(Request(self.url+path,data=data,headers=headers),timeout=3) as response:
            return response.status,response.read()

    def test_report_and_dashboard(self):
        send(self.url,'office-01',self.token,self.data)
        status,body=self.request('/api/v1/status',self.admin)
        self.assertEqual(status,200)
        rows=json.loads(body)['agents']
        self.assertEqual(rows[0]['report'],self.data)
        self.assertEqual(rows[0]['status'],'Reporting')
        self.assertEqual(rows[1]['status'],'Never seen')
        self.assertIn(b'BreakCheck / Fleet',self.request('/',self.admin,basic=True)[1])
        revised=dict(self.data,broken_links=2)
        send(self.url,'office-01',self.token,revised)
        rows=json.loads(self.request('/api/v1/status',self.admin)[1])['agents']
        self.assertEqual(rows[0]['status'],'Attention')
        self.assertEqual(rows[0]['report'],revised)

    def test_separate_credentials(self):
        for path,token,data in [('/',None,None),('/api/v1/status',self.token,None),
                                ('/api/v1/report/office-02',self.token,json.dumps(self.data).encode()),
                                ('/api/v1/report/office-01',self.admin,json.dumps(self.data).encode())]:
            with self.assertRaises(HTTPError) as exc:
                self.request(path,token,data)
            self.assertEqual(exc.exception.code,401)

    def test_reject_extra_fields_and_large_body(self):
        for data in [json.dumps(dict(self.data,path='/private')).encode(),b'x'*4097,b'{}',
                     json.dumps(dict(self.data,files=True)).encode()]:
            with self.assertRaises(HTTPError) as exc:
                self.request('/api/v1/report/office-01',self.token,data)
            self.assertEqual(exc.exception.code,400)

    def test_stale_and_revocation(self):
        send(self.url,'office-01',self.token,self.data)
        _,keys=credentials(self.admin,self.keys)
        store=FleetStore(self.db,keys)
        rows=store.rows(now=10**12)
        self.assertEqual(rows[0]['status'],'Stale')
        reduced=FleetStore(self.db,{'office-02':keys['office-02']})
        self.assertEqual(len(reduced.rows()),1)
        self.assertEqual(store.rows()[0]['status'],'Never seen')

    def test_aggregation_never_includes_paths(self):
        from unittest.mock import Mock
        index=Mock()
        index.refresh.side_effect=[Snapshot(3,18,[(1,'Deleted','secret.txt','')],[('private.html','secret.txt')],[]),
                                   Snapshot(1,2,[],[],['private path'],False),
                                   OSError('private error path')]
        report=collect([self.base/'private1',self.base/'private2',self.base/'private3'],60,index)
        self.assertEqual((report['files'],report['broken_links'],report['partial'],report['errors']),(4,1,1,1))
        self.assertNotIn('private',json.dumps(report))
        self.assertNotIn('secret',json.dumps(report))

    def test_https_and_enrollment_validation(self):
        for url in ('http://example.com','https://user:pw@example.com','https://example.com/path','file:///tmp/file'):
            with self.assertRaises(ValueError):
                endpoint(url)
        self.assertEqual(endpoint('https://example.com/'),'https://example.com')
        with self.assertRaises(ValueError):
            credentials(self.admin,{'office':self.admin})
        with self.assertRaises(ValueError):
            validate_report(dict(self.data,partial=2))
