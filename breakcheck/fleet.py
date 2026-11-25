"""Opt-in fleet telemetry: only bounded aggregate counters, no file paths."""
from __future__ import annotations

import json
import os
import re
import signal
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from . import __version__
from .agent import validated_root
from .safety import SafetyIndex

ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
TOKEN = re.compile(r'[A-Za-z0-9_-]{32,128}')
COUNTERS = ('folders','files','logical_bytes','broken_links','partial','errors')
MAX_BODY = 4096


def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):
        raise ValueError('Agent ID must contain 1–64 ASCII letters, digits, dots, hyphens or underscores.')
    return value


def secret(value):
    if not isinstance(value,str) or not TOKEN.fullmatch(value) or value.startswith('REPLACE_WITH_'):
        raise ValueError('Configure a random token of 32–128 URL-safe characters.')
    return value


def validate_report(data):
    if not isinstance(data,dict) or set(data)!=set(COUNTERS)|{'version','interval'}:
        raise ValueError('Unexpected report fields.')
    if not isinstance(data['version'],str) or not re.fullmatch(r'[0-9]{1,8}\.[0-9]{1,8}\.[0-9]{1,8}',data['version']):
        raise ValueError('Invalid version.')
    for key in COUNTERS:
        if type(data[key]) is not int or not 0<=data[key]<=2**63-1:
            raise ValueError('Invalid report counter.')
    if not 1<=data['folders']<=32 or data['partial']+data['errors']>data['folders']:
        raise ValueError('Invalid coverage counters.')
    if type(data['interval']) is not int or not 30<=data['interval']<=86400:
        raise ValueError('Invalid interval.')
    return data


def collect(roots,interval,index=None):
    index=index if index is not None else SafetyIndex()
    data=dict.fromkeys(COUNTERS,0)
    data.update(version=__version__,interval=interval,folders=len(roots))
    for root in roots:
        try:
            snap=index.refresh(root)
            data['files']+=snap.files
            data['logical_bytes']+=snap.bytes
            if snap.complete:
                data['broken_links']+=len(snap.alerts)
            else:
                data['partial']+=1
        except Exception:
            # Paths, exception messages, history and file contents never leave
            # the endpoint. Report only a failed-folder count.
            data['errors']+=1
    return validate_report(data)


def endpoint(url):
    parts=urlsplit(url)
    if (parts.scheme not in ('https','http') or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ('','/')):
        raise ValueError('Server must be an HTTPS origin, without credentials or path.')
    if parts.scheme=='http' and parts.hostname not in ('127.0.0.1','::1','localhost'):
        raise ValueError('Plain HTTP is allowed only for local testing.')
    return url.rstrip('/')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def send(url,agent,token,data):
    url,agent,token=endpoint(url),identifier(agent),secret(token)
    data=validate_report(data)
    req=Request(url+'/api/v1/report/'+agent,
                data=json.dumps(data,separators=(',',':')).encode(),
                headers={'Authorization':'Bearer '+token,'Content-Type':'application/json',
                         'User-Agent':'BreakCheck-fleet'},method='POST')
    with build_opener(NoRedirect()).open(req,timeout=10) as response:
        if response.status!=204:
            raise OSError('Unexpected server response.')


def run_agent(roots,url,agent,token,interval=60,once=False,stop=None):
    roots=list(dict.fromkeys(validated_root(p) for p in roots))
    if not 1<=len(roots)<=32 or not 30<=interval<=86400:
        raise ValueError('Provide 1–32 folders and an interval of 30–86400 seconds.')
    for a in roots:
        if any(a!=b and a.is_relative_to(b) for b in roots):
            raise ValueError('Do not specify overlapping project folders.')
    endpoint(url)
    identifier(agent)
    secret(token)
    stop=stop if stop is not None else threading.Event()
    while not stop.is_set():
        data=collect(roots,interval)
        if stop.is_set():
            break
        try:
            send(url,agent,token,data)
            print(json.dumps(data),flush=True)
            if once:
                return int(bool(data['partial'] or data['errors']))
        except (OSError,ValueError):
            print('Fleet report delivery failed; check connection and credentials.',file=sys.stderr,flush=True)
            if once:
                return 1
        stop.wait(interval)
    return 0


def agent_command(args):
    stop=threading.Event()
    old={}
    for sig in (signal.SIGINT,signal.SIGTERM):
        old[sig]=signal.signal(sig,lambda *_:stop.set())
    try:
        return run_agent(args.folders,args.server,args.id,os.environ.get('BREAKCHECK_AGENT_TOKEN',''),
                         args.interval,args.once,stop)
    finally:
        for sig,handler in old.items():
            signal.signal(sig,handler)
