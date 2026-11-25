"""Opt-in release lookup; never downloads or executes software."""
import json
import re
from urllib.request import Request,urlopen
from . import __version__

URL='https://api.github.com/repos/PCTestAdmin/BreakCheck/releases/latest'
RELEASES='https://github.com/PCTestAdmin/BreakCheck/releases'

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'v?[0-9]{1,8}\.[0-9]{1,8}\.[0-9]{1,8}',value):
        raise ValueError('Unexpected release version.')
    return tuple(map(int,value.lstrip('v').split('.')))

def check_update():
    request=Request(URL,headers={'Accept':'application/vnd.github+json','User-Agent':'BreakCheck-update-check'})
    with urlopen(request,timeout=8) as response:
        data=response.read(256*1024+1)
    if len(data)>256*1024:
        raise ValueError('Release response too large.')
    payload=json.loads(data)
    if not isinstance(payload,dict):
        raise ValueError('Invalid release response.')
    latest=payload.get('tag_name')
    return {'current':__version__,'latest':latest,'available':version(latest)>version(__version__),'url':RELEASES}
