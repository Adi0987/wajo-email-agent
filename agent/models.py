"""Shared data types."""
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class Level(IntEnum):
    """Autonomy levels, ordered from most cautious to most autonomous.

    min() of several levels gives the most cautious one.
    """
    ESCALATE = 0  # do nothing, flag the email
    ASK = 1       # wait for approval
    NOTIFY = 2    # act, tell the user, allow undo
    SILENT = 3    # act


@dataclass(frozen=True)
class Email:
    id: str
    thread_id: str
    sender: str                    # exact address, lowercase
    to: tuple[str, ...]
    subject: str
    body: str
    sent_at: datetime
    authenticated: bool = True     # passed sender authentication
    has_unsubscribe: bool = False  # has a List-Unsubscribe header


@dataclass(frozen=True)
class Action:
    kind: str                      # see checks.ACTIONS
    email_id: str
    label: str = ""                # for "label"
    to: tuple[str, ...] = ()       # for "send" and "forward"
    body: str = ""                 # for "draft_reply" and "send"


@dataclass(frozen=True)
class Flags:
    """Check 2 results for one email and proposed action."""
    money: bool = False
    injection: bool = False
