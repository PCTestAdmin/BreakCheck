"""Exercise the actual packaged CLI against a loopback fleet server."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.request import Request,urlopen
from urllib.error import URLError
import socket

def main():
    command=sys.argv[1:]
    if not command:
        raise ValueError('Provide CLI executable and optional arguments.')
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory).resolve()
        project=base/'project'
        project.mkdir()
        (project/'test.txt').write_text('test',encoding='utf-8')
        admin=secrets.token_urlsafe(32)
        agent=secrets.token_urlsafe(32)
        env=dict(os.environ,BREAKCHECK_ADMIN_TOKEN=admin,BREAKCHECK_AGENT_TOKENS=json.dumps({'smoke':agent}),
                 BREAKCHECK_AGENT_TOKEN=agent,BREAKCHECK_STATE_DIR=str(base/'agent-state'))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        request=Request(url+'/api/v1/status',headers={'Authorization':'Bearer '+admin})
        server=subprocess.Popen(command+['fleet-server','--port',str(port),'--db',str(base/'fleet.sqlite3')],env=env)
        try:
            for attempt in range(100):
                if server.poll() is not None:
                    raise RuntimeError('Fleet server exited early.')
                try:
                    with urlopen(request,timeout=1) as response:
                        assert json.load(response)['agents'][0]['status']=='Never seen'
                    break
                except (URLError,OSError):
                    time.sleep(.2)
            else:
                raise RuntimeError('Fleet server not ready.')
            subprocess.run(command+['fleet-agent',str(project),'--server',url,'--id','smoke','--once'],env=env,check=True,timeout=45)
            with urlopen(request,timeout=3) as response:
                row=json.load(response)['agents'][0]
            assert row['report']['files']==1 and row['status']=='Reporting'
            assert str(project) not in json.dumps(row)
            print('PASS: packaged Fleet server and agent')
        finally:
            if os.name=='nt':
                subprocess.run(['taskkill.exe','/PID',str(server.pid),'/T','/F'],capture_output=True,timeout=10,check=False)
            else:
                server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)

if __name__=='__main__':
    main()
