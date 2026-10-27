from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints, ConfigDict

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
Status = Literal['new', 'in_progress', 'done']
class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
class ParticipantIn(Input):
    name: Name
class MeetingIn(Input):
    title: Title
    date: date
    participant_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1)
class DecisionIn(Input):
    text: Text
class TaskIn(Input):
    decision_id: int = Field(gt=0)
    description: Text
    responsible_id: int = Field(gt=0)
    deadline: date
    status: Status = 'new'
class StatusIn(Input):
    status: Status
