"""Messages from the agent to the user, outside the chat."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from agent.models import Action

@dataclass(frozen=True)
class Notice:
    kind: str                         # notify, ask, escalate, nudge, reminder or remind_me (asked for by the user)
    email_id: str
    at: datetime
    action: Optional[Action] = None
    approval_id: str = ""
