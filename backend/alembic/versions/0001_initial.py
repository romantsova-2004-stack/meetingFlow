"""Initial MeetingFlow schema."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('participants',sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String(120),nullable=False),sa.CheckConstraint('length(trim(name)) > 0'))
    op.create_table('meetings',sa.Column('id',sa.Integer,primary_key=True),sa.Column('title',sa.String(150),nullable=False),sa.Column('date',sa.Date,nullable=False),sa.Column('created_at',sa.DateTime,nullable=False),sa.Column('updated_at',sa.DateTime,nullable=False),sa.CheckConstraint('length(trim(title)) BETWEEN 1 AND 150'))
    op.create_index('ix_meetings_date','meetings',['date'])
    op.create_table('meeting_participants',sa.Column('meeting_id',sa.Integer,sa.ForeignKey('meetings.id',ondelete='RESTRICT'),primary_key=True),sa.Column('participant_id',sa.Integer,sa.ForeignKey('participants.id',ondelete='RESTRICT'),primary_key=True))
    op.create_table('decisions',sa.Column('id',sa.Integer,primary_key=True),sa.Column('meeting_id',sa.Integer,sa.ForeignKey('meetings.id',ondelete='RESTRICT'),nullable=False),sa.Column('text',sa.Text,nullable=False),sa.Column('created_at',sa.DateTime,nullable=False),sa.CheckConstraint('length(trim(text)) > 0'))
    op.create_index('ix_decisions_meeting_id','decisions',['meeting_id'])
    op.create_table('tasks',sa.Column('id',sa.Integer,primary_key=True),sa.Column('decision_id',sa.Integer,sa.ForeignKey('decisions.id',ondelete='RESTRICT'),nullable=False),sa.Column('description',sa.Text,nullable=False),sa.Column('responsible_id',sa.Integer,sa.ForeignKey('participants.id',ondelete='RESTRICT'),nullable=False),sa.Column('deadline',sa.Date,nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.Column('created_at',sa.DateTime,nullable=False),sa.Column('updated_at',sa.DateTime,nullable=False),sa.CheckConstraint("status IN ('new','in_progress','done')"),sa.CheckConstraint('length(trim(description)) > 0'))
    for col in ['decision_id','deadline','status']: op.create_index('ix_tasks_'+col,'tasks',[col])
def downgrade():
    for table in ['tasks','decisions','meeting_participants','meetings','participants']: op.drop_table(table)
