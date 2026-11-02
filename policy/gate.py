"""The gate: every action the agent takes goes through here.

It decides how much the user is involved (silent, notify, ask, escalate) with three checks:
two fixed safety rules and one learned rate. It is the only holder of the mail tools that change
anything (through the executor), it learns from the user's feedback, and it runs the scheduler.
The agent (agent/wajo.py) proposes; the gate decides and enforces.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from policy.checks import USER_ONLY, action_check, email_check, is_external
from policy.executor import Executor
from policy.flags import detect_flags
from policy.mail_client import MailClient
from policy.models import Action, Email, Level
from policy.notices import Notice
from policy.rates import ApprovalRates
from policy.scheduler import Scheduler
from policy.senders import other_party
from policy.timing import Timing


@dataclass
class Outcome:
    """What the gate did with one action."""

    action: Action
    level: Level
    executed: bool
    checks: dict
    outside: bool = False  # escalated because it would go to an address outside the thread and contacts


class Gate:
    def __init__(self, mail: MailClient, rates: Optional[ApprovalRates] = None):
        self.mail = mail
        self.rates = rates or ApprovalRates()
        self.timing = Timing()
        self.scheduler = Scheduler(mail, self.timing, self.wants_follow_up)
        self.notices: list[Notice] = []  # everything that needs the user, in order
        self.executor = Executor(mail, self.checks_for, self.notices)
        self.labels: dict[str, dict] = {}  # classifier output per email
        self.history: list[dict] = []  # every piece of feedback, for the agent's memory

    # --- what the agent sends in ---

    def classified(self, email_id: str, labels: dict) -> None:
        self.labels[email_id] = labels
        if labels.get("deadline"):
            self.scheduler.add_deadline(email_id, labels["deadline"])

    def submit(self, action: Action, now: datetime) -> Outcome:
        """An action the agent proposes on its own. The gate picks the level and acts on it."""
        if action.kind in USER_ONLY:  # the agent never writes or sends a reply on its own
            action = Action("keep", action.email_id)
        return self._handle(action, now)

    def request(self, action: Action, now: datetime) -> Outcome:
        """An action the user asked for. It counts as their approval, except for anything that leaves the
        mailbox (send, forward, unsubscribe): those always become a question showing exactly what will go out.
        The checks still apply either way."""
        if is_external(action.kind):
            return self._handle(action, now)
        executed = self.executor.run_requested(action, now)
        entry = self.executor.log[-1]
        return Outcome(action, Level.ASK, executed, entry["checks"])

    def tick(self, now: datetime) -> None:
        """Adds follow-ups and reminders that are due to the notices."""
        for email in self.scheduler.due_follow_ups(now):
            self.notices.append(Notice("nudge", email.id, now))
        for email in self.scheduler.due_reminders(now):
            self.notices.append(Notice("reminder", email.id, now))
        for email in self.scheduler.due_requested(now):
            self.notices.append(Notice("remind_me", email.id, now))

    def _handle(self, action: Action, now: datetime) -> Outcome:
        level = self.executor.handle(action, now)
        entry = self.executor.log[-1]
        outside = (
            level == Level.ESCALATE
            and detect_flags(
                self.mail.get(action.email_id), action, self.labels.get(action.email_id, {}), self.mail
            ).outside
        )
        return Outcome(action, level, entry["executed"], entry["checks"], outside)

    # --- the three checks ---

    def kind_of(self, email: Email) -> str:
        """The kind of email (newsletter, spam, request, ...), from the classifier."""
        return self.labels.get(email.id, {}).get("kind", "other")

    def flags_for(self, action: Action):
        """Check 2's flags (money, manipulation) for this action on its email."""
        return detect_flags(self.mail.get(action.email_id), action, self.labels.get(action.email_id, {}), self.mail)

    def checks_for(self, action: Action) -> dict[str, Level]:
        email = self.mail.get(action.email_id)
        sender, _ = other_party(email, self.mail)
        flags = self.flags_for(action)
        return {
            "action": action_check(action.kind),
            "email": email_check(action.kind, flags),
            "learned": self.learned_level(action, sender, email),
        }

    def learned_level(self, action: Action, sender: str, email: Email) -> Level:
        level = self.rates.level(action.kind, sender, self.kind_of(email))
        if action.kind == "keep":
            return max(level, Level.NOTIFY)  # leaving it alone needs no permission; the user is told
        return level

    def wants_follow_up(self, sent: Email) -> bool:
        """Whether to nudge about this unanswered message: yes, unless the user has said these aren't needed."""
        if any(self.labels.get(e.id, {}).get("injection") for e in self.mail.thread(sent.thread_id)):
            return False  # never chase a thread that started as an attack
        recipient, category = other_party(sent, self.mail)
        return not self.rates.declined("follow_up", recipient, category)

    # --- the user's feedback ---

    def approve(self, notice: Notice, now: datetime) -> bool:
        self.executor.approve(notice.approval_id)
        self._record(notice.action, approved=True)
        return self.executor.run_approved(notice.approval_id, notice.action, now)

    def reject(self, notice: Notice, chosen: Optional[str] = None) -> None:
        self.executor.reject(notice.approval_id)
        self._record(notice.action, approved=False, chosen=chosen)

    def confirm(self, notice: Notice) -> None:
        """The user says a notified action was right."""
        self._record(notice.action, approved=True)

    def undo(self, action: Action, chosen: Optional[str] = None) -> bool:
        undone = self.executor.undo(action)
        self._record(action, approved=False, chosen=chosen)
        return undone

    def do_instead(self, action: Action, now: datetime) -> bool:
        """Runs what the user asked for instead. Feedback is recorded by reject/undo with `chosen`."""
        return self.request(action, now).executed

    def remind(self, email_id: str, at: datetime) -> None:
        self.scheduler.remind(email_id, at)

    def cancel_scheduled(self, email_id: str) -> int:
        return self.scheduler.cancel(email_id)

    def timing_feedback(self, notice: Notice, verdict: str, days: Optional[float] = None) -> str:
        """verdict: "too_early", "too_late", "ok", or for a nudge "not_needed". `days`: what the user said they
        prefer, if they said. Returns the new setting in words, if it changed."""
        sent = self.mail.get(notice.email_id)
        recipient, category = other_party(sent, self.mail)
        if notice.kind == "nudge":
            self.rates.record("follow_up", recipient, category, approved=verdict != "not_needed")
            if days:
                self.timing.wait[category] = days
            else:
                self.timing.nudge_feedback(category, verdict)
            return (
                f"Follow-ups now wait {self.timing.wait[category]:g} days." if days or verdict.startswith("too") else ""
            )
        if notice.kind == "reminder":
            if days:
                self.timing.lead[category] = days
            else:
                self.timing.reminder_feedback(category, verdict)
            return (
                f"Deadline reminders now come {self.timing.lead[category]:g} days before."
                if days or verdict.startswith("too")
                else ""
            )
        return ""

    def _record(self, action: Action, approved: bool, chosen: Optional[str] = None) -> None:
        """Learns triage preferences. Replies are always the user's own request, so they aren't learned."""
        email = self.mail.get(action.email_id)
        sender, _ = other_party(email, self.mail)
        kind = self.kind_of(email)
        attack = self.labels.get(email.id, {}).get("injection", False)  # what the user does with an attack
        if action.kind not in USER_ONLY and not attack:  # says nothing about their preferences
            self.rates.record(action.kind, sender, kind, approved)
        if chosen and chosen not in USER_ONLY and not attack:
            self.rates.record(chosen, sender, kind, approved=True)
        if action.kind not in USER_ONLY:
            self.history.append(
                {
                    "email_id": email.id,
                    "sender": sender,
                    "kind": kind,
                    "subject": email.subject,
                    "proposed": action.kind,
                    "label": action.label,
                    "approved": approved,
                    "chosen": chosen,
                }
            )
