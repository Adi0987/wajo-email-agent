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
    def __init__(self, mailbox: Mailbox, checks_for: Callable[[Action], dict[str, Level]],
                 notices: list[Notice]):
        self.mailbox = mailbox
        self.checks_for = checks_for   # action -> {"action": Level, "email": Level, "learned": Level}
        self.notices = notices         # owned by the agent; the executor adds notify, ask, escalate
        self.approvals = Approvals()
        self.log: list[dict] = []      # every decision, read by the eval

    def level_for(self, action: Action) -> tuple[Level, dict[str, Level]]:
        checks = self.checks_for(action)
        return min(checks.values()), checks

    def handle(self, action: Action, now: datetime) -> Level:
        level, checks = self.level_for(action)
        if level in (Level.SILENT, Level.NOTIFY):
            self.mailbox.apply(action, now)
            if level == Level.NOTIFY:
                self.notices.append(Notice("notify", action.email_id, now, action))
        elif level == Level.ASK:
            approval_id = self.approvals.request(action)
            self.notices.append(Notice("ask", action.email_id, now, action, approval_id))
        else:
            self.notices.append(Notice("escalate", action.email_id, now, action))
        self._record(now, action, level, checks, executed=level >= Level.NOTIFY)
        return level

    def approve(self, approval_id: str) -> None:
        self.approvals.approve(approval_id)

    def reject(self, approval_id: str) -> None:
        self.approvals.reject(approval_id)

    def run_approved(self, approval_id: str, action: Action, now: datetime) -> bool:
        """Run an approved action if it is unchanged and still allowed."""
        level, checks = self.level_for(action)
        allowed = self.approvals.use(approval_id, action) and level >= Level.ASK
        if allowed:
            self.mailbox.apply(action, now)
        self._record(now, action, Level.ASK, checks, executed=allowed, approved=True)
        return allowed

    def undo(self, action: Action) -> None:
        self.mailbox.undo(action)

    def _record(self, now: datetime, action: Action, level: Level, checks: dict[str, Level],
                executed: bool, approved: bool = False) -> None:
        self.log.append({"at": now, "action": action, "level": level, "checks": checks,
                         "executed": executed, "approved": approved})
