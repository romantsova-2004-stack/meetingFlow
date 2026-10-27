import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .database import get_db
from .models import Participant, Meeting, Decision, Task
from .schemas import ParticipantIn, MeetingIn, DecisionIn, TaskIn, StatusIn

app = FastAPI(title='MeetingFlow API', version='1.0.0', description='Встречи → решения → задачи')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','), allow_methods=['GET','POST','PUT','PATCH'], allow_headers=['Content-Type'])

def today():
    return datetime.now(ZoneInfo(os.getenv('APP_TIMEZONE', 'Europe/Moscow'))).date()

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    errors=[]
    for e in exc.errors():
        kind=e['type']
        message='Проверьте значение поля'
        if kind=='missing': message='Обязательное поле'
        elif 'date' in kind: message='Укажите корректную календарную дату'
        elif kind in ('string_too_short','too_short'): message='Поле не может быть пустым'
        elif kind=='string_too_long': message='Превышена допустимая длина'
        elif kind=='literal_error': message='Выберите допустимый статус'
        errors.append({'field':str(e['loc'][-1]),'message':message})
    return JSONResponse(status_code=422, content={'detail':'Проверьте обязательные поля', 'errors':errors})

@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(status_code=409, content={'detail':'Не удалось сохранить: проверьте связи и обязательные поля'})

@app.exception_handler(Exception)
async def server_error(request: Request, exc):
    logging.exception('API error', exc_info=exc)
    return JSONResponse(status_code=500, content={'detail':'Не удалось выполнить запрос. Повторите попытку.'})

def get(db, model, id):
    obj=db.get(model,id)
    if obj is None: raise HTTPException(404, 'Запись не найдена')
    return obj

def person(p): return {'id':p.id,'name':p.name}
def task_data(t):
    return {'id':t.id,'description':t.description,'decision_id':t.decision_id,'responsible_id':t.responsible_id,'responsible':person(t.responsible),'deadline':t.deadline,'status':t.status,'is_overdue':t.deadline < today() and t.status != 'done','created_at':t.created_at,'updated_at':t.updated_at,'decision':{'id':t.decision.id,'text':t.decision.text,'meeting_id':t.decision.meeting_id},'meeting':{'id':t.decision.meeting.id,'title':t.decision.meeting.title,'date':t.decision.meeting.date}}
def decision_data(d): return {'id':d.id,'meeting_id':d.meeting_id,'text':d.text,'created_at':d.created_at,'tasks':[task_data(t) for t in sorted(d.tasks,key=lambda t:(t.deadline,t.id))]}
def meeting_data(m): return {'id':m.id,'title':m.title,'date':m.date,'participants':[person(p) for p in m.participants],'decisions':[decision_data(d) for d in sorted(m.decisions,key=lambda d:d.id)],'created_at':m.created_at,'updated_at':m.updated_at}

@app.get('/api/health')
def health(): return {'status':'ok'}
@app.get('/api/participants')
def participants(db: Session=Depends(get_db)):
    return [person(p) for p in db.scalars(select(Participant).order_by(Participant.name,Participant.id))]
@app.post('/api/participants',status_code=201)
def create_participant(data: ParticipantIn,db: Session=Depends(get_db)):
    p=Participant(**data.model_dump()); db.add(p); db.commit(); return person(p)
@app.get('/api/meetings')
def meetings(sort: Literal['asc','desc']='desc',db: Session=Depends(get_db)):
    order=Meeting.date.asc() if sort=='asc' else Meeting.date.desc()
    return [meeting_data(m) for m in db.scalars(select(Meeting).order_by(order,Meeting.id.desc()))]
def save_meeting(m,data,db):
    people=[get(db,Participant,id) for id in dict.fromkeys(data.participant_ids)]
    m.title=data.title; m.date=data.date; m.participants=people
    db.add(m); db.commit(); db.refresh(m); return meeting_data(m)
@app.post('/api/meetings',status_code=201)
def create_meeting(data: MeetingIn,db: Session=Depends(get_db)): return save_meeting(Meeting(),data,db)
@app.get('/api/meetings/{id}')
def meeting(id:int,db: Session=Depends(get_db)): return meeting_data(get(db,Meeting,id))
@app.put('/api/meetings/{id}')
def edit_meeting(id:int,data: MeetingIn,db: Session=Depends(get_db)): return save_meeting(get(db,Meeting,id),data,db)
@app.get('/api/meetings/{id}/decisions')
def decisions(id:int,db: Session=Depends(get_db)): return [decision_data(d) for d in get(db,Meeting,id).decisions]
@app.post('/api/meetings/{id}/decisions',status_code=201)
def create_decision(id:int,data: DecisionIn,db: Session=Depends(get_db)):
    get(db,Meeting,id); d=Decision(meeting_id=id,text=data.text); db.add(d); db.commit(); return decision_data(d)
@app.get('/api/decisions/{id}')
def decision(id:int,db: Session=Depends(get_db)): return decision_data(get(db,Decision,id))
@app.get('/api/tasks')
def tasks(status: Literal['new','in_progress','done']|None=None, incomplete:bool=False, overdue:bool=False, sort:Literal['asc','desc']='asc',db: Session=Depends(get_db)):
    stmt=select(Task)
    if status: stmt=stmt.where(Task.status==status)
    if incomplete: stmt=stmt.where(Task.status!='done')
    if overdue: stmt=stmt.where(Task.status!='done',Task.deadline<today())
    stmt=stmt.order_by(Task.deadline.asc() if sort=='asc' else Task.deadline.desc(),Task.id)
    return [task_data(t) for t in db.scalars(stmt)]
@app.get('/api/tasks/incomplete')
def incomplete_tasks(db: Session=Depends(get_db)): return tasks(incomplete=True,db=db)
def save_task(t,data,db):
    get(db,Decision,data.decision_id); get(db,Participant,data.responsible_id)
    for key,value in data.model_dump().items(): setattr(t,key,value)
    db.add(t); db.commit(); db.refresh(t); return task_data(t)
@app.post('/api/tasks',status_code=201)
def create_task(data:TaskIn,db: Session=Depends(get_db)): return save_task(Task(),data,db)
@app.get('/api/tasks/{id}')
def task(id:int,db: Session=Depends(get_db)): return task_data(get(db,Task,id))
@app.put('/api/tasks/{id}')
def edit_task(id:int,data:TaskIn,db: Session=Depends(get_db)): return save_task(get(db,Task,id),data,db)
@app.patch('/api/tasks/{id}/status')
def change_status(id:int,data:StatusIn,db: Session=Depends(get_db)):
    t=get(db,Task,id); t.status=data.status; db.commit(); db.refresh(t); return task_data(t)
@app.get('/api/dashboard')
def dashboard(db: Session=Depends(get_db)):
    count=lambda model,*where: db.scalar(select(func.count()).select_from(model).where(*where))
    return {'meetings':count(Meeting),'tasks':count(Task),'incomplete':count(Task,Task.status!='done'),'overdue':count(Task,Task.status!='done',Task.deadline<today()),'upcoming_tasks':tasks(incomplete=True,db=db)[:5],'recent_meetings':meetings(db=db)[:4],'today':today()}
