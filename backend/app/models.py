from datetime import date, datetime, timezone
from sqlalchemy import String, Text, ForeignKey, Date, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now():
    return datetime.now(timezone.utc)

class Participant(Base):
    __tablename__ = 'participants'
    __table_args__ = (CheckConstraint('length(trim(name)) > 0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))

class MeetingParticipant(Base):
    __tablename__ = 'meeting_participants'
    meeting_id: Mapped[int] = mapped_column(ForeignKey('meetings.id', ondelete='RESTRICT'), primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey('participants.id', ondelete='RESTRICT'), primary_key=True)

class Meeting(Base):
    __tablename__ = 'meetings'
    __table_args__ = (CheckConstraint('length(trim(title)) BETWEEN 1 AND 150'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    participants: Mapped[list[Participant]] = relationship(secondary='meeting_participants', lazy='selectin')
    decisions: Mapped[list['Decision']] = relationship(back_populates='meeting', lazy='selectin')

class Decision(Base):
    __tablename__ = 'decisions'
    __table_args__ = (CheckConstraint('length(trim(text)) > 0'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey('meetings.id', ondelete='RESTRICT'), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    meeting: Mapped[Meeting] = relationship(back_populates='decisions')
    tasks: Mapped[list['Task']] = relationship(back_populates='decision', lazy='selectin')

class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (CheckConstraint("status IN ('new','in_progress','done')"), CheckConstraint('length(trim(description)) > 0'))
    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey('decisions.id', ondelete='RESTRICT'), index=True)
    description: Mapped[str] = mapped_column(Text)
    responsible_id: Mapped[int] = mapped_column(ForeignKey('participants.id', ondelete='RESTRICT'))
    deadline: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default='new', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    decision: Mapped[Decision] = relationship(back_populates='tasks')
    responsible: Mapped[Participant] = relationship(lazy='joined')
