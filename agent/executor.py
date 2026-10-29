"""The only code that changes the mailbox.

It reruns the checks before every action, so nothing upstream can skip them.
"""
from datetime import datetime
from typing import Callable

from agent.approvals import Approvals
from agent.mailbox import Mailbox
from agent.models import Action, Level
from agent.notices import Notice


class Executor:
    def __init__(self, mailbox: Mailbox, level_for: Callable[[Action], Level]):
        self.mailbox = mailbox
        self.level_for = level_for
        self.approvals = Approvals()
        self.notices: list[Notice] = []
        self.log: list[dict] = []   # every decision, read by the eval

    def handle(self, action: Action, now: datetime) -> Level:
        level = self.level_for(action)
        if level in (Level.SILENT, Level.NOTIFY):
            self.mailbox.apply(action, now)
            if level == Level.NOTIFY:
                self.notices.append(Notice("notify", action.email_id, now, action))
        elif level == Level.ASK:
            approval_id = self.approvals.request(action)
            self.notices.append(Notice("ask", action.email_id, now, action, approval_id))
        else:
            self.notices.append(Notice("escalate", action.email_id, now, action))
        self._record(now, action, level, executed=level >= Level.NOTIFY)
        return level

    def run_approved(self, approval_id: str, action: Action, now: datetime) -> bool:
        """Run an approved action if it is unchanged and still allowed."""
        allowed = self.approvals.matches(approval_id, action) and self.level_for(action) >= Level.ASK
        if allowed:
            self.mailbox.apply(action, now)
        self.approvals.approved.pop(approval_id, None)
        self._record(now, action, Level.ASK, executed=allowed, approved=True)
        return allowed

    def undo(self, action: Action) -> None:
        self.mailbox.undo(action)

    def _record(self, now: datetime, action: Action, level: Level, executed: bool, approved: bool = False) -> None:
        self.log.append({"at": now, "action": action, "level": level,
                         "executed": executed, "approved": approved})
