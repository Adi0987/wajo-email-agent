"""Wires the parts together: queue in, decisions out, feedback back."""
from collections import deque
from datetime import datetime
from typing import Callable, Optional

from agent.checks import action_check, email_check
from agent.executor import Executor
from agent.flags import detect_flags
from agent.mailbox import Mailbox
from agent.models import Action, Email, Level
from agent.notices import Notice
from agent.rates import ApprovalRates
from agent.scheduler import Scheduler
from agent.senders import other_party
from agent.timing import Timing

FOLLOW_UP_BODY = "Just following up on my last email."


class Agent:
    def __init__(self, mailbox: Mailbox,
                 propose: Callable[[Email, Mailbox, Optional[str]], Action],
                 classify: Callable[[Email], dict],
                 rates: Optional[ApprovalRates] = None):
        self.mailbox = mailbox
        self.propose = propose      # LLM: suggests an action, given the user's usual choice
        self.classify = classify    # LLM: money, injection, deadline labels
        self.rates = rates or ApprovalRates()
        self.timing = Timing()
        self.scheduler = Scheduler(mailbox, self.timing)
        self.notices: list[Notice] = []    # everything sent to the user, in order
        self.executor = Executor(mailbox, self.checks_for, self.notices)
        self.labels: dict[str, dict] = {}
        self.queue: deque[Email] = deque()

    # --- background work ---

    def on_new_mail(self, email: Email) -> None:
        self.queue.append(email)

    def tick(self, now: datetime) -> None:
        """One pass of the background worker."""
        for email in self.scheduler.due_follow_ups(now):
            self.notices.append(Notice("nudge", email.id, now))
            self.executor.handle(Action("draft_reply", email.id, body=FOLLOW_UP_BODY), now)
        for email in self.scheduler.due_reminders(now):
            self.notices.append(Notice("reminder", email.id, now))
        while self.queue:
            self._handle(self.queue.popleft(), now)

    def _handle(self, email: Email, now: datetime) -> None:
        labels = self.classify(email)
        self.labels[email.id] = labels
        if labels.get("deadline"):
            self.scheduler.add_deadline(email.id, labels["deadline"])
        sender, category = other_party(email, self.mailbox)
        usual = self.rates.usual_choice(sender, category)
        self.executor.handle(self.propose(email, self.mailbox, usual), now)

    # --- the three checks ---

    def checks_for(self, action: Action) -> dict[str, Level]:
        email = self.mailbox.get(action.email_id)
        sender, category = other_party(email, self.mailbox)
        flags = detect_flags(email, action, self.labels.get(email.id, {}), self.mailbox)
        return {
            "action": action_check(action.kind),
            "email": email_check(action.kind, flags),
            "learned": self.rates.level(action.kind, sender, category),
        }

    # --- user feedback ---

    def approve(self, notice: Notice, now: datetime) -> bool:
        self.executor.approve(notice.approval_id)
        self._record(notice.action, approved=True)
        return self.executor.run_approved(notice.approval_id, notice.action, now)

    def reject(self, notice: Notice, chosen: Optional[str] = None) -> None:
        self.executor.reject(notice.approval_id)
        self._record(notice.action, approved=False, chosen=chosen)

    def confirm(self, notice: Notice) -> None:
        """User marks a notified action as correct."""
        self._record(notice.action, approved=True)

    def undo(self, action: Action, chosen: Optional[str] = None) -> None:
        self.executor.undo(action)
        self._record(action, approved=False, chosen=chosen)

    def timing_feedback(self, notice: Notice, verdict: str) -> None:
        """verdict: "too_early", "too_late" or "ok"."""
        _, category = other_party(self.mailbox.get(notice.email_id), self.mailbox)
        if notice.kind == "nudge":
            self.timing.nudge_feedback(category, verdict)
        elif notice.kind == "reminder":
            self.timing.reminder_feedback(category, verdict)

    def _record(self, action: Action, approved: bool, chosen: Optional[str] = None) -> None:
        sender, category = other_party(self.mailbox.get(action.email_id), self.mailbox)
        self.rates.record(action.kind, sender, category, approved)
        if chosen:
            self.rates.record(chosen, sender, category, approved=True)
