from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db, make_engine
from app.main import app, today
from app.seed import seed
from app import seed as seed_module

@pytest.fixture
def storage(tmp_path):
    url=f'sqlite:///{tmp_path / "test.db"}'
    engine=make_engine(url)
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    def override():
        with factory() as db: yield db
    app.dependency_overrides[get_db]=override
    with TestClient(app) as client: yield client,engine,factory,url
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def flow(storage):
    c=storage[0]
    p=c.post('/api/participants',json={'name':' Анна Романцова '}); assert p.status_code==201
    p=p.json()
    m=c.post('/api/meetings',json={'title':'Планирование','date':str(today()),'participant_ids':[p['id']]});assert m.status_code==201
    m=m.json()
    d=c.post(f'/api/meetings/{m["id"]}/decisions',json={'text':'Выпустить MVP'});assert d.status_code==201
    d=d.json()
    data={'description':'Проверить первый сценарий','decision_id':d['id'],'responsible_id':p['id'],'deadline':str(today()+timedelta(days=1))}
    t=c.post('/api/tasks',json=data);assert t.status_code==201
    return c,p,m,d,t.json(),data

def test_ac01_to_ac10_full_flow_and_restart(flow,storage):
    c,p,m,d,t,data=flow
    assert p['name']=='Анна Романцова'
    assert c.get('/api/meetings').json()[0]['id']==m['id']
    assert c.get(f'/api/meetings/{m["id"]}').json()['decisions'][0]['id']==d['id']
    assert t['decision']['id']==d['id'] and t['meeting']['id']==m['id']
    assert t['status']=='new'
    endpoint=f'/api/tasks/{t["id"]}'
    assert c.patch(endpoint+'/status',json={'status':'in_progress'}).json()['status']=='in_progress'
    assert t['id'] in [x['id'] for x in c.get('/api/tasks/incomplete').json()]
    assert c.patch(endpoint+'/status',json={'status':'done'}).status_code==200
    assert c.get('/api/tasks?incomplete=true').json()==[]
    assert c.get('/api/dashboard').json()['incomplete']==0
    storage[1].dispose()
    second_engine=make_engine(storage[3]);factory=sessionmaker(second_engine)
    def new_session():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=new_session
    with TestClient(app) as reopened:
        restored=reopened.get(endpoint).json()
        assert restored['status']=='done' and restored['meeting']['title']==m['title']
        assert reopened.get('/api/meetings').json()[0]['decisions'][0]['tasks'][0]['id']==t['id']
    second_engine.dispose()

@pytest.mark.parametrize('payload',[
 {},{'title':' ','date':'2026-01-01','participant_ids':[1]},
 {'title':'Встреча','date':'2026-02-30','participant_ids':[1]},
 {'title':'Встреча','date':'2026-01-01','participant_ids':[]},
 {'title':'x'*151,'date':'2026-01-01','participant_ids':[1]},
])
def test_meeting_validation(storage,payload):
    r=storage[0].post('/api/meetings',json=payload)
    assert r.status_code==422 and r.json()['errors']

@pytest.mark.parametrize('field,value',[('description',' '),('responsible_id',None),('deadline',None),('deadline','2026-13-01'),('decision_id',None),('status','bad')])
def test_task_validation(flow,field,value):
    c,_,_,_,_,data=flow
    data[field]=value
    assert c.post('/api/tasks',json=data).status_code==422

@pytest.mark.parametrize('field',['responsible_id','deadline','decision_id','description'])
def test_required_task_fields(flow,field):
    c,_,_,_,_,data=flow;del data[field]
    assert c.post('/api/tasks',json=data).status_code==422

def test_editing_and_many_tasks(flow):
    c,p,m,d,t,data=flow
    new_person=c.post('/api/participants',json={'name':'Михаил'}).json()
    r=c.put(f'/api/meetings/{m["id"]}',json={'title':'Обновлённая встреча','date':str(today()),'participant_ids':[p['id'],new_person['id']]})
    assert r.status_code==200 and len(r.json()['participants'])==2
    data.update(description='Изменённая задача',responsible_id=new_person['id'])
    assert c.put(f'/api/tasks/{t["id"]}',json=data).json()['responsible_id']==new_person['id']
    assert c.post('/api/tasks',json=data).status_code==201
    assert len(c.get(f'/api/decisions/{d["id"]}').json()['tasks'])==2

def test_overdue_and_sorting(flow):
    c,p,m,d,t,data=flow
    data['deadline']=str(today()-timedelta(days=1))
    old=c.post('/api/tasks',json=data).json();assert old['is_overdue']
    assert c.get('/api/tasks?overdue=true').json()[0]['id']==old['id']
    assert c.get('/api/tasks?sort=asc').json()[0]['id']==old['id']
    assert c.get('/api/tasks?sort=desc').json()[0]['id']==t['id']
    assert c.get('/api/dashboard').json()['overdue']==1
    data['deadline']=str(today())
    assert not c.post('/api/tasks',json=data).json()['is_overdue']
    c.patch(f'/api/tasks/{old["id"]}/status',json={'status':'done'})
    assert not c.get(f'/api/tasks/{old["id"]}').json()['is_overdue']
    assert c.get('/api/dashboard').json()['overdue']==0
    assert len(c.get('/api/tasks?status=done').json())==1

def test_invalid_references_and_missing_records(flow):
    c,p,m,d,t,data=flow
    data['decision_id']=9999
    assert c.post('/api/tasks',json=data).status_code==404
    data['decision_id']=d['id'];data['responsible_id']=9999
    assert c.post('/api/tasks',json=data).status_code==404
    for route in ['/meetings/9999','/tasks/9999','/decisions/9999','/meetings/9999/decisions']:
        assert c.get('/api'+route).status_code==404
    assert c.post('/api/meetings/9999/decisions',json={'text':'Test'}).status_code==404
    assert c.patch(f'/api/tasks/{t["id"]}/status',json={'status':'bad'}).status_code==422
    assert c.post(f'/api/meetings/{m["id"]}/decisions',json={'text':' '}).status_code==422

def test_database_integrity(flow,storage):
    c,p,m,d,t,data=flow
    with storage[1].connect() as conn:
        assert conn.execute(text('PRAGMA foreign_keys')).scalar()==1
        for sql in [f'DELETE FROM meetings WHERE id={m["id"]}',f'DELETE FROM decisions WHERE id={d["id"]}',f"UPDATE tasks SET status='invalid' WHERE id={t['id']}",f'UPDATE tasks SET responsible_id=99999 WHERE id={t["id"]}']:
            with pytest.raises(IntegrityError):conn.execute(text(sql))
            conn.rollback()

def test_seed_is_idempotent_and_preserves_user_data(flow,storage,monkeypatch):
    monkeypatch.setattr(seed_module,'SessionLocal',storage[2]);seed();seed()
    c=flow[0]
    assert len(c.get('/api/meetings').json())==4
    assert c.get('/api/meetings/1').json()['title']=='Планирование'
    assert len(c.get('/api/tasks').json())==8

def test_migration_matches_models(tmp_path):
    import subprocess,os,sys
    db=tmp_path/'migrated.db'
    env={**os.environ,'DATABASE_URL':f'sqlite:///{db}'}
    subprocess.run([sys.executable,'-m','alembic','-c','alembic.ini','upgrade','head'],env=env,check=True)
    from alembic.migration import MigrationContext
    from alembic.autogenerate import compare_metadata
    engine=make_engine(f'sqlite:///{db}')
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn),Base.metadata)==[]
    engine.dispose()
