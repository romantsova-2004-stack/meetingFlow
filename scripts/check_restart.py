"""Verify persistence across a real backend process restart using an isolated database."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
PY=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
BASE='http://127.0.0.1:8001'
def request(path,method='GET',data=None):
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(BASE+path,data=body,method=method,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
def start(env):
    p=subprocess.Popen([str(PY),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001'],cwd=ROOT/'backend',env=env,stdout=subprocess.DEVNULL)
    for _ in range(100):
        if p.poll() is not None:raise RuntimeError('Backend exited')
        try:request('/api/health');return p
        except OSError:time.sleep(.1)
    p.terminate();raise RuntimeError('Backend did not become ready')
def stop(p):
    p.terminate();p.wait(timeout=10)
with tempfile.TemporaryDirectory(prefix='meetingflow-restart-') as directory:
    env={**os.environ,'DATABASE_URL':f'sqlite:///{Path(directory)/"restart.db"}'}
    subprocess.run([str(PY),'-m','alembic','-c','alembic.ini','upgrade','head'],cwd=ROOT/'backend',env=env,check=True)
    p=start(env)
    try:
        person=request('/api/participants','POST',{'name':'Проверка перезапуска'})
        m=request('/api/meetings','POST',{'title':'Сохранение между процессами','date':'2026-10-27','participant_ids':[person['id']]})
        d=request(f'/api/meetings/{m["id"]}/decisions','POST',{'text':'Проверить постоянное хранение'})
        t=request('/api/tasks','POST',{'description':'Перезапустить backend','decision_id':d['id'],'responsible_id':person['id'],'deadline':'2026-10-28'})
        request(f'/api/tasks/{t["id"]}/status','PATCH',{'status':'done'})
    finally:stop(p)
    p=start(env)
    try:
        restored=request(f'/api/tasks/{t["id"]}')
        assert restored['status']=='done'
        assert restored['decision']['id']==d['id']
        assert restored['meeting']['id']==m['id']
        assert request('/api/meetings')[0]['participants'][0]['id']==person['id']
        assert request('/api/tasks/incomplete')==[]
        print('PASS: после остановки и запуска нового backend-процесса встреча, участник, решение, задача и статус сохранены.')
    finally:stop(p)
