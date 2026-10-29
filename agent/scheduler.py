"""Finds follow-ups and deadline reminders that are due."""
from datetime import datetime, timedelta

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

    def add_deadline(self, email_id: str, deadline: datetime) -> None:
        self.deadlines[email_id] = deadline

    def due_follow_ups(self, now: datetime) -> list[Email]:
        """The user's last message in each thread, if unanswered for N days."""
        due = []
        for thread_id in {e.thread_id for e in self.mailbox.emails.values()}:
            last = self.mailbox.thread(thread_id)[-1]
            if last.sender != self.mailbox.user_address or last.id in self.done:
                continue
            _, category = other_party(last, self.mailbox)
            if now - last.sent_at >= timedelta(days=self.timing.n[category]):
                self.done.add(last.id)
                due.append(last)
        return due

    def due_reminders(self, now: datetime) -> list[Email]:
        """Emails whose deadline is L days away or closer."""
        due = []
        for email_id, deadline in self.deadlines.items():
            if email_id in self.done:
                continue
            email = self.mailbox.get(email_id)
            _, category = other_party(email, self.mailbox)
            if now >= deadline - timedelta(days=self.timing.l[category]):
                self.done.add(email_id)
                due.append(email)
        return due
