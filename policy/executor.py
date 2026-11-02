"""The only code that changes mail: it holds the mail client's write tools.

It reruns the checks before every action, so nothing upstream can skip them.
"""

from datetime import datetime
from typing import Callable

from policy.approvals import Approvals
from policy.mail_client import MailClient
from policy.models import Action, Level
from policy.notices import Notice


class Executor:
    def __init__(self, mailbox: MailClient, checks_for: Callable[[Action], dict[str, Level]], notices: list[Notice]):
        self.mailbox = mailbox
        self.checks_for = checks_for  # action -> {"action": Level, "email": Level, "learned": Level}
        self.notices = notices  # owned by the agent; the executor adds notify, ask, escalate
        self.approvals = Approvals()
        self.log: list[dict] = []  # every decision, read by the eval

    def level_for(self, action: Action) -> tuple[Level, dict[str, Level]]:
        checks = self.checks_for(action)
        return min(checks.values()), checks

    def handle(self, action: Action, now: datetime) -> Level:
        level, checks = self.level_for(action)
        executed = False
        if level in (Level.SILENT, Level.NOTIFY):
            executed = self.mailbox.act(action)["ok"]  # done only if the mail server says so
            if executed and level == Level.NOTIFY:
                self.notices.append(Notice("notify", action.email_id, now, action))
        elif level == Level.ASK:
            approval_id = self.approvals.request(action)
            self.notices.append(Notice("ask", action.email_id, now, action, approval_id))
        else:
            self.notices.append(Notice("escalate", action.email_id, now, action))
        self._record(now, action, level, checks, executed=executed)
        return level

    def approve(self, approval_id: str) -> None:
        self.approvals.approve(approval_id)

    def reject(self, approval_id: str) -> None:
        self.approvals.reject(approval_id)

    def run_approved(self, approval_id: str, action: Action, now: datetime) -> bool:
        """Run an approved action if it is unchanged and still allowed."""
        level, checks = self.level_for(action)
        allowed = self.approvals.use(approval_id, action) and level >= Level.ASK
        executed = allowed and self.mailbox.act(action)["ok"]
        self._record(now, action, Level.ASK, checks, executed=executed, approved=True)
        return executed

    def run_requested(self, action: Action, now: datetime) -> bool:
        """The user asked for this exact action, so their request is the approval. The checks still apply."""
        approval_id = self.approvals.request(action)
        self.approvals.approve(approval_id)
        return self.run_approved(approval_id, action, now)

    def undo(self, action: Action) -> bool:
        return self.mailbox.undo(action)["ok"]

    def _record(
        self,
        now: datetime,
        action: Action,
        level: Level,
        checks: dict[str, Level],
        executed: bool,
        approved: bool = False,
    ) -> None:
        self.log.append(
            {"at": now, "action": action, "level": level, "checks": checks, "executed": executed, "approved": approved}
        )
