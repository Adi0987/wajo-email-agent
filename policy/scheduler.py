"""Finds follow-ups and deadline reminders that are due."""

from datetime import datetime, timedelta
from typing import Callable, Optional

from policy.mail_client import MailClient
from policy.models import Email
from policy.senders import other_party
from policy.timing import Timing


class Scheduler:
    def __init__(self, mailbox: MailClient, timing: Timing, wants_follow_up: Callable[[Email], bool] = lambda e: True):
        self.mailbox = mailbox
        self.timing = timing
        self.wants_follow_up = wants_follow_up  # learned: the user can say follow-ups aren't needed
        self.deadlines: dict[str, datetime] = {}  # email id -> deadline
        self.done: set[str] = set()  # ids already nudged or reminded
        self.started: Optional[datetime] = None  # set on the first tick; older threads are never chased
        self.requested: dict[str, datetime] = {}  # email id -> when the user asked to be reminded

    def add_deadline(self, email_id: str, deadline: datetime) -> None:
        self.deadlines[email_id] = deadline

    def remind(self, email_id: str, at: datetime) -> None:
        """A reminder the user asked for, e.g. "remind me tomorrow to respond"."""
        self.requested[email_id] = at

    def cancel(self, email_id: str) -> int:
        """Cancels whatever is scheduled for this email's thread. Returns how many items were cancelled."""
        before = len(self.pending())
        thread = self.mailbox.thread(self.mailbox.get(email_id).thread_id)
        self.done.update(e.id for e in thread)
        for e in thread:
            self.requested.pop(e.id, None)
        return before - len(self.pending())

    def pending(self) -> list[dict]:
        """Follow-ups and reminders that haven't fired yet, soonest first.

        Each: {"kind": "follow_up", "reminder" or "requested", "email": Email, "category": str, "at": when it fires}.
        """
        items = [
            {"kind": "requested", "email": self.mailbox.get(email_id), "category": "", "at": at}
            for email_id, at in self.requested.items()
        ]
        for last in self.mailbox.latest_in_threads():
            if last.sender != self.mailbox.user_address or last.id in self.done or not self.wants_follow_up(last):
                continue
            if self.started and last.sent_at < self.started:
                continue  # older than the agent: never chased
            if any(self.mailbox.status(e.id)["trashed"] for e in self.mailbox.thread(last.thread_id)):
                continue  # the user binned the thread
            _, category = other_party(last, self.mailbox)
            items.append(
                {
                    "kind": "follow_up",
                    "email": last,
                    "category": category,
                    "at": last.sent_at + timedelta(days=self.timing.wait[category]),
                }
            )
        for email_id, deadline in self.deadlines.items():
            if email_id in self.done:
                continue
            email = self.mailbox.get(email_id)
            _, category = other_party(email, self.mailbox)
            at = deadline - timedelta(days=self.timing.lead[category])
            if at <= email.sent_at:
                continue  # due too soon to remind: the user just saw it arrive
            items.append({"kind": "reminder", "email": email, "category": category, "deadline": deadline, "at": at})
        return sorted(items, key=lambda item: item["at"])

    def due_follow_ups(self, now: datetime) -> list[Email]:
        """The user's last message in each thread, if sent after the agent started, unanswered for N days,
        and the user hasn't said follow-ups like this aren't needed."""
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
