"""Messages from the agent to the user, outside the chat."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from agent.models import Action

KINDS = ("notify", "ask", "escalate", "nudge", "reminder")


@dataclass(frozen=True)
class Notice:
    kind: str
    email_id: str
    at: datetime
    action: Optional[Action] = None
    approval_id: str = ""
