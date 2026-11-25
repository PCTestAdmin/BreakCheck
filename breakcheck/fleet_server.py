"""Small self-hosted fleet collector. Deploy behind an HTTPS reverse proxy."""
from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import base64
import json
import os
from pathlib import Path
import sqlite3
import time

from .fleet import identifier,secret,validate_report,MAX_BODY


def hashed(value):
    return hashlib.sha256(value.encode()).digest()


def credentials(admin, agents):
    admin=secret(admin)
    if not isinstance(agents,dict) or not 1<=len(agents)<=1000:
        raise ValueError('Configure 1–1000 enrolled agent IDs and individual tokens.')
    seen={admin}
    keys={}
    for name,token in agents.items():
        identifier(name)
        secret(token)
        if token in seen:
            raise ValueError('Every agent and admin must have a distinct token.')
        seen.add(token)
        keys[name]=hashed(token)
    return hashed(admin),keys


class FleetStore:
    def __init__(self,path,keys):
        self.path=Path(path)
        self.keys=keys
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with closing(self.connect()) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS reports (agent TEXT PRIMARY KEY, received INTEGER NOT NULL, report TEXT NOT NULL)')
            # Revoking an agent removes its stored report as well.
            for (name,) in db.execute('SELECT agent FROM reports').fetchall():
                if name not in keys:
                    db.execute('DELETE FROM reports WHERE agent=?',(name,))

    def connect(self):
        return sqlite3.connect(self.path,timeout=5)

    def put(self,name,data):
        if name not in self.keys:
            raise ValueError('Unknown agent.')
        validate_report(data)
        with closing(self.connect()) as db,db:
            db.execute('INSERT INTO reports VALUES(?,?,?) ON CONFLICT(agent) DO UPDATE SET received=excluded.received,report=excluded.report',
                       (name,int(time.time()),json.dumps(data,separators=(',',':'))))

    def rows(self,now=None):
        now=int(time.time()) if now is None else now
        with closing(self.connect()) as db:
            received={name:(stamp,json.loads(data)) for name,stamp,data in db.execute('SELECT agent,received,report FROM reports')}
        out=[]
        for name in sorted(self.keys):
            item=received.get(name)
            if item is None:
                out.append({'agent':name,'status':'Never seen','received':None,'report':None})
            else:
                stamp,data=item
                # Interval is a requested wait after each scan, not an SLA.
                age=max(0,now-stamp)
                status='Stale' if age>max(180,3*data['interval']) else ('Attention' if data['broken_links'] or data['errors'] or data['partial'] else 'Reporting')
                out.append({'agent':name,'status':status,'received':stamp,'report':data})
        return out


def dashboard(rows):
    esc=lambda v:html.escape(str(v),quote=True)
    counts={s:sum(r['status']==s for r in rows) for s in ('Reporting','Attention','Stale','Never seen')}
    cards=''.join(f'<div class="metric"><small>{esc(s)}</small><strong>{n}</strong></div>' for s,n in counts.items())
    body=[]
    for row in rows:
        report=row['report']
        fields=[row['agent'],row['status']]
        if report:
            fields += [report['version'],report['folders'],report['files'],f"{report['logical_bytes']/1024**3:,.2f}",
                       report['broken_links'],report['partial'],report['errors'],time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime(row['received']))]
        else:
            fields+=['—']*8
        body.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in fields)+'</tr>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>BreakCheck Fleet</title><style>body{background:#111827;color:#edf2f7;font:15px system-ui;margin:32px}'
            'h1{font-size:30px}small,p{color:#a5b4c7}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin:24px 0}'
            '.metric{background:#1c2636;padding:20px;border-radius:10px}.metric strong{display:block;font-size:28px;margin-top:8px}'
            '.table{overflow:auto;background:#1c2636;border-radius:10px}table{border-collapse:collapse;width:100%;white-space:nowrap}'
            'th,td{text-align:left;padding:12px;border-bottom:1px solid #344258}th{color:#a5b4c7}a{color:#93c5fd}</style></head>'
            '<body><h1>BreakCheck / Fleet</h1><p>Local project monitoring · Aggregate telemetry only</p>'
            '<div class="metrics">'+cards+'</div><p><a href="/">Refresh</a> · <a href="/api/v1/status">JSON status</a></p>'
            '<div class="table"><table><thead><tr>'+''.join('<th>'+s+'</th>' for s in ('Agent','Status','Version','Folders','Files','Logical GiB','Known broken links','Partial folders','Errors','Last report'))+
            '</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'
            '<p>Counts refer to observed project files; incomplete scans may miss broken links. Stale agents may be offline or scanning. No remote file access.</p></body></html>').encode()


def make_server(host,port,db,admin,agents):
    admin_hash,keys=credentials(admin,agents)
    store=FleetStore(db,keys)

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.0'
        def setup(self):
            self.request.settimeout(10)
            super().setup()

        def log_message(self,*args):
            # Do not log credentials, submitted data or arbitrary URL strings.
            pass

        def reply(self,status,body=b'',kind='text/plain; charset=utf-8',challenge=False):
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header('Referrer-Policy','no-referrer')
            if challenge:
                self.send_header('WWW-Authenticate','Basic realm="BreakCheck Fleet", charset="UTF-8"')
            self.end_headers()
            if body:
                self.wfile.write(body)

        def admin(self):
            auth=self.headers.get('Authorization','')
            try:
                if auth.startswith('Basic '):
                    user,token=base64.b64decode(auth[6:],validate=True).decode('ascii').split(':',1)
                    return user=='admin' and hmac.compare_digest(hashed(secret(token)),admin_hash)
                if auth.startswith('Bearer '):
                    return hmac.compare_digest(hashed(secret(auth[7:])),admin_hash)
            except (ValueError,UnicodeError):
                pass
            return False

        def do_GET(self):
            if self.path not in ('/','/api/v1/status'):
                self.reply(404)
                return
            if not self.admin():
                self.reply(401,challenge=True)
                return
            try:
                rows=store.rows()
                if self.path=='/':
                    self.reply(200,dashboard(rows),'text/html; charset=utf-8')
                else:
                    self.reply(200,json.dumps({'agents':rows}).encode(),'application/json')
            except sqlite3.Error:
                self.reply(503)

        def do_POST(self):
            prefix='/api/v1/report/'
            if not self.path.startswith(prefix):
                self.reply(404)
                return
            name=self.path[len(prefix):]
            auth=self.headers.get('Authorization','')
            try:
                identifier(name)
                allowed=name in keys and auth.startswith('Bearer ') and hmac.compare_digest(hashed(secret(auth[7:])),keys[name])
            except ValueError:
                allowed=False
            if not allowed:
                self.reply(401)
                return
            try:
                if self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/json':
                    raise ValueError('Invalid body.')
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=MAX_BODY:
                    raise ValueError('Invalid body length.')
                raw=self.rfile.read(length)
                if len(raw)!=length:
                    raise ValueError('Incomplete body.')
                data=validate_report(json.loads(raw))
                store.put(name,data)
            except (ValueError,UnicodeError,RecursionError):
                self.reply(400)
                return
            except sqlite3.Error:
                self.reply(503)
                return
            self.reply(204)

    return HTTPServer((host,port),Handler)


def serve(args):
    admin=os.environ.get('BREAKCHECK_ADMIN_TOKEN','')
    raw=os.environ.get('BREAKCHECK_AGENT_TOKENS','{}')
    if len(raw)>256*1024:
        raise ValueError('Enrollment configuration too large.')
    agents=json.loads(raw)
    if args.host!='127.0.0.1' and not args.trusted_proxy:
        raise ValueError('Non-loopback binding requires --trusted-proxy and a private reverse-proxy network.')
    with make_server(args.host,args.port,args.db,admin,agents) as server:
        print(f'BreakCheck Fleet listening on {args.host}:{args.port}',flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
