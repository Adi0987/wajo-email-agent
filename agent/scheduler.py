"""Finds follow-ups and deadline reminders that are due."""
from datetime import datetime, timedelta
from typing import Optional

from agent.mailbox import Mailbox
from agent.models import Email
from agent.senders import other_party
from agent.timing import Timing


class Scheduler:
    def __init__(self, mailbox: Mailbox, timing: Timing):
        self.mailbox = mailbox
        self.timing = timing
        self.deadlines: dict[str, datetime] = {}   # email id -> deadline
        self.done: set[str] = set()                # ids already nudged or reminded
        self.started: Optional[datetime] = None    # set on the first tick; older threads are never chased
        self.requested: dict[str, datetime] = {}   # email id -> when the user asked to be reminded

    def add_deadline(self, email_id: str, deadline: datetime) -> None:
        self.deadlines[email_id] = deadline

    def remind(self, email_id: str, at: datetime) -> None:
        """A reminder the user asked for, e.g. "remind me tomorrow to respond"."""
        self.requested[email_id] = at

    def pending(self) -> list[dict]:
        """Follow-ups and reminders that haven't fired yet, soonest first.

        Each: {"kind": "follow_up", "reminder" or "requested", "email": Email, "category": str, "at": when it fires}.
        """
        items = [{"kind": "requested", "email": self.mailbox.get(email_id), "category": "", "at": at}
                 for email_id, at in self.requested.items()]
        for thread_id in {e.thread_id for e in self.mailbox.emails.values()}:
            last = self.mailbox.thread(thread_id)[-1]
            if last.sender != self.mailbox.user_address or last.id in self.done:
                continue
            if self.started and last.sent_at < self.started:
                continue                   # older than the agent: never chased
            _, category = other_party(last, self.mailbox)
            items.append({"kind": "follow_up", "email": last, "category": category,
                          "at": last.sent_at + timedelta(days=self.timing.n[category])})
        for email_id, deadline in self.deadlines.items():
            if email_id in self.done:
                continue
            email = self.mailbox.get(email_id)
            _, category = other_party(email, self.mailbox)
            items.append({"kind": "reminder", "email": email, "category": category, "deadline": deadline,
                          "at": deadline - timedelta(days=self.timing.l[category])})
        return sorted(items, key=lambda item: item["at"])

    def due_follow_ups(self, now: datetime) -> list[Email]:
        """The user's last message in each thread, if sent after the agent started and unanswered for N days."""
        self.started = self.started or now
        return self._due("follow_up", now)

    def due_reminders(self, now: datetime) -> list[Email]:
        """Emails whose deadline is L days away or closer."""
        return self._due("reminder", now)

    def due_requested(self, now: datetime) -> list[Email]:
        """Reminders the user asked for, once their time comes."""
        due = [self.mailbox.get(i) for i, at in self.requested.items() if at <= now]
        for email in due:
            del self.requested[email.id]
        return due

    def _due(self, kind: str, now: datetime) -> list[Email]:
        due = [item["email"] for item in self.pending() if item["kind"] == kind and item["at"] <= now]
        self.done.update(email.id for email in due)
        return due
