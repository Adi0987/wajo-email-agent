"""In-memory mock mailbox. Only the executor calls apply() and undo()."""
from collections import defaultdict
from datetime import datetime

from agent.models import Action, Email


class Mailbox:
    def __init__(self, user_address: str):
        self.user_address = user_address.lower()
        self.user_domain = self.user_address.split("@")[1]
        self.emails: dict[str, Email] = {}
        self.labels: dict[str, set[str]] = defaultdict(set)
        self.archived: set[str] = set()
        self.read: set[str] = set()
        self.trashed: set[str] = set()
        self.drafts: dict[str, str] = {}
        self.forwarded: list[Action] = []
        self.unsubscribed: set[str] = set()

    # --- incoming mail (the outside world, not the agent) ---

    def receive(self, email: Email) -> None:
        self.emails[email.id] = email

    # --- reads ---

    def get(self, email_id: str) -> Email:
        return self.emails[email_id]

    def thread(self, thread_id: str) -> list[Email]:
        messages = [e for e in self.emails.values() if e.thread_id == thread_id]
        return sorted(messages, key=lambda e: e.sent_at)

    def contacts(self) -> set[str]:
        """Addresses the user has sent mail to."""
        sent = [e for e in self.emails.values() if e.sender == self.user_address]
        return {address for e in sent for address in e.to}

    # --- writes (executor only) ---

    def apply(self, action: Action, now: datetime) -> None:
        email = self.get(action.email_id)
        if action.kind == "label":
            self.labels[email.id].add(action.label)
        elif action.kind == "archive":
            self.archived.add(email.id)
        elif action.kind == "mark_read":
            self.read.add(email.id)
        elif action.kind == "trash":
            self.trashed.add(email.id)
        elif action.kind == "draft_reply":
            self.drafts[email.id] = action.body
        elif action.kind == "send":
            self.drafts.pop(email.id, None)
            self.receive(Email(
                id=f"{email.id}-reply", thread_id=email.thread_id,
                sender=self.user_address, to=action.to,
                subject=f"Re: {email.subject}", body=action.body, sent_at=now,
            ))
        elif action.kind == "forward":
            self.forwarded.append(action)
        elif action.kind == "unsubscribe":
            self.unsubscribed.add(email.sender)
        else:
            raise ValueError(f"unknown action: {action.kind}")

    def undo(self, action: Action) -> None:
        email_id = action.email_id
        if action.kind == "label":
            self.labels[email_id].discard(action.label)
        elif action.kind == "archive":
            self.archived.discard(email_id)
        elif action.kind == "mark_read":
            self.read.discard(email_id)
        elif action.kind == "trash":
            self.trashed.discard(email_id)
        elif action.kind == "draft_reply":
            self.drafts.pop(email_id, None)
        else:
            raise ValueError(f"cannot undo: {action.kind}")
