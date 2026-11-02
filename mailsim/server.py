"""A simulated mail server. It exposes MCP-style tools, the way a real mail provider's
MCP server would. The agent only ever talks to it through those tools (agent/mail_client.py),
so it can't tell this is a simulation: a send returns a 200 and a message id.

Not part of the agent. The outside world (the eval, the app) delivers mail with deliver().
"""

import itertools
import json
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from typing import Callable

from policy.models import Email


def result(payload: dict, error: bool = False) -> dict:
    """An MCP tool result."""
    return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": error}


def as_dict(email: Email) -> dict:
    return {
        "id": email.id,
        "thread_id": email.thread_id,
        "from": email.sender,
        "to": list(email.to),
        "subject": email.subject,
        "body": email.body,
        "date": email.sent_at.isoformat(),
        "authenticated": email.authenticated,
        "list_unsubscribe": email.has_unsubscribe,
    }


class MailServer:
    def __init__(self, user_address: str):
        self.user_address = user_address.lower()
        self.now = datetime.now()  # the server's clock; the simulation moves it
        self.emails: dict[str, Email] = {}
        self.labels: dict[str, set[str]] = defaultdict(set)
        self.archived: set[str] = set()
        self.read: set[str] = set()
        self.trashed: set[str] = set()
        self.drafts: dict[str, str] = {}
        self.forwarded: list[dict] = []
        self.unsubscribed: set[str] = set()
        self._ids = itertools.count(1)
        self.tools: dict[str, Callable[..., dict]] = {
            "get_profile": self.get_profile,
            "get_email": self.get_email,
            "list_thread": self.list_thread,
            "list_threads": self.list_threads,
            "list_contacts": self.list_contacts,
            "search_emails": self.search_emails,
            "archive_email": self.archive_email,
            "unarchive_email": self.unarchive_email,
            "label_email": self.label_email,
            "unlabel_email": self.unlabel_email,
            "mark_read": self.mark_read,
            "mark_unread": self.mark_unread,
            "trash_email": self.trash_email,
            "untrash_email": self.untrash_email,
            "create_draft": self.create_draft,
            "delete_draft": self.delete_draft,
            "send_email": self.send_email,
            "forward_email": self.forward_email,
            "unsubscribe": self.unsubscribe,
        }

    # --- the outside world ---

    def deliver(self, email: Email) -> None:
        self.emails[email.id] = email

    def receive(self, email: Email) -> Email:
        """Delivers an email as arriving now: the server stamps it with its own clock, as a real one would."""
        email = replace(email, sent_at=self.now)
        self.deliver(email)
        return email

    # --- the MCP endpoint ---

    def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in self.tools:
            return result({"status": 404, "error": f"unknown tool {name}"}, error=True)
        try:
            return result({"status": 200, **self.tools[name](**arguments)})
        except KeyError as missing:
            return result({"status": 404, "error": f"not found: {missing}"}, error=True)

    # --- read tools ---

    def get_profile(self) -> dict:
        return {"address": self.user_address, "domain": self.user_address.split("@")[1]}

    def get_email(self, id: str) -> dict:
        return {
            "email": as_dict(self.emails[id]),
            "labels": sorted(self.labels.get(id, ())),
            "archived": id in self.archived,
            "trashed": id in self.trashed,
            "read": id in self.read,
            "draft": self.drafts.get(id, ""),
        }

    def _thread(self, thread_id: str) -> list[Email]:
        return sorted((e for e in self.emails.values() if e.thread_id == thread_id), key=lambda e: e.sent_at)

    def list_thread(self, thread_id: str) -> dict:
        return {"messages": [as_dict(e) for e in self._thread(thread_id)]}

    def list_threads(self) -> dict:
        """The latest message of every thread."""
        latest: dict[str, Email] = {}
        for email in self.emails.values():
            if email.thread_id not in latest or email.sent_at >= latest[email.thread_id].sent_at:
                latest[email.thread_id] = email
        return {"threads": [{"thread_id": t, "last_message": as_dict(e)} for t, e in latest.items()]}

    def folder_of(self, email: Email) -> str:
        if email.id in self.trashed:
            return "trash"
        if email.sender == self.user_address:
            return "sent"
        return "archived" if email.id in self.archived else "inbox"

    def search_emails(self, folder: str = "all", query: str = "", sender: str = "", limit: int = 20) -> dict:
        """Emails in a folder (inbox, archived, trash, sent, drafts or all), newest first, optionally matching
        a sender or text. Returns the total and up to `limit` of them."""
        query, sender = query.lower(), sender.lower()
        found = [
            e
            for e in sorted(self.emails.values(), key=lambda e: e.sent_at, reverse=True)
            if (folder == "all" or (folder == "drafts" and e.id in self.drafts) or self.folder_of(e) == folder)
            and sender in e.sender
            and (query in e.subject.lower() or query in e.body.lower())
        ]
        return {
            "total": len(found),
            "emails": [
                {
                    "id": e.id,
                    "from": e.sender,
                    "to": list(e.to),
                    "subject": e.subject,
                    "date": e.sent_at.isoformat(),
                    "folder": self.folder_of(e),
                    "labels": sorted(self.labels.get(e.id, ())),
                    "has_draft": e.id in self.drafts,
                }
                for e in found[:limit]
            ],
        }

    def list_contacts(self) -> dict:
        sent = [e for e in self.emails.values() if e.sender == self.user_address]
        return {"contacts": sorted({address for e in sent for address in e.to})}

    # --- write tools ---

    def archive_email(self, id: str) -> dict:
        self.emails[id]
        self.archived.add(id)
        return {"id": id}

    def unarchive_email(self, id: str) -> dict:
        self.archived.discard(id)
        return {"id": id}

    def label_email(self, id: str, label: str) -> dict:
        self.emails[id]
        self.labels[id].add(label)
        return {"id": id, "label": label}

    def unlabel_email(self, id: str, label: str) -> dict:
        self.labels[id].discard(label)
        return {"id": id, "label": label}

    def mark_read(self, id: str) -> dict:
        self.emails[id]
        self.read.add(id)
        return {"id": id}

    def mark_unread(self, id: str) -> dict:
        self.read.discard(id)
        return {"id": id}

    def trash_email(self, id: str) -> dict:
        self.emails[id]
        self.trashed.add(id)
        return {"id": id}

    def untrash_email(self, id: str) -> dict:
        self.trashed.discard(id)
        return {"id": id}

    def create_draft(self, reply_to: str, body: str) -> dict:
        self.emails[reply_to]
        self.drafts[reply_to] = body
        return {"draft_for": reply_to}

    def delete_draft(self, reply_to: str) -> dict:
        self.drafts.pop(reply_to, None)
        return {"draft_for": reply_to}

    def send_email(self, reply_to: str, to: list, body: str) -> dict:
        original = self.emails[reply_to]
        subject = original.subject if original.subject.lower().startswith("re:") else f"Re: {original.subject}"
        message_id = f"sent-{next(self._ids)}"
        self.deliver(
            Email(
                id=message_id,
                thread_id=original.thread_id,
                sender=self.user_address,
                to=tuple(to),
                subject=subject,
                body=body,
                sent_at=self.now,
            )
        )
        self.drafts.pop(reply_to, None)
        return {"message_id": message_id, "thread_id": original.thread_id}

    def forward_email(self, id: str, to: list) -> dict:
        self.emails[id]
        self.forwarded.append({"id": id, "to": list(to)})
        return {"id": id, "to": list(to)}

    def unsubscribe(self, id: str) -> dict:
        self.unsubscribed.add(self.emails[id].sender)
        return {"id": id}


def connect(user_address: str):
    """A new simulated mail server, and the agent's MCP client for it."""
    from policy.mail_client import MailClient

    server = MailServer(user_address)
    return server, MailClient(server.call_tool)
