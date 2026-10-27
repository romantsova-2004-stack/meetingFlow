from datetime import timedelta
from sqlalchemy import select
from .database import SessionLocal
from .models import Participant,Meeting,Decision,Task
from .main import today

def seed():
    with SessionLocal() as db:
        names=['Анна Романцова','Михаил Волков','Елена Смирнова','Дмитрий Соколов']
        people=[]
        for name in names:
            p=db.scalar(select(Participant).where(Participant.name==name))
            if not p: p=Participant(name=name); db.add(p); db.flush()
            people.append(p)
        samples=[('Планирование продуктового спринта',-1,'Сфокусироваться на первом пользовательском сценарии.',[('Подготовить прототип карточки встречи',2,'in_progress'),('Согласовать критерии готовности',-2,'new'),('Описать пользовательский путь',-3,'done')]),('Синхронизация команды',-3,'Обновить документацию и распределить ответственность.',[('Обновить документацию REST API',4,'new'),('Проверить адаптивную вёрстку',1,'in_progress')]),('Итоги исследования пользователей',-5,'Упростить процесс фиксации договорённостей.',[('Собрать результаты интервью',-1,'done'),('Подготовить список улучшений',7,'new')])]
        for title,offset,text,tasks in samples:
            if db.scalar(select(Meeting).where(Meeting.title==title)): continue
            m=Meeting(title=title,date=today()+timedelta(days=offset),participants=people[:3]); db.add(m); db.flush()
            d=Decision(meeting_id=m.id,text=text); db.add(d); db.flush()
            for i,(desc,days,status) in enumerate(tasks): db.add(Task(decision_id=d.id,description=desc,responsible_id=people[i%len(people)].id,deadline=today()+timedelta(days=days),status=status))
        db.commit()
    print('Демонстрационные данные готовы. Пользовательские записи сохранены.')
if __name__=='__main__': seed()
