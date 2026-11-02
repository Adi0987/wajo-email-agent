"""The agent's only way to reach the mailbox: MCP tool calls to the user's mail server.

Read methods are for the whole agent. act() and undo() change mail and are used only by the
executor. Every result comes back from the server; an action counts as done only if it succeeded.
"""

import json
from datetime import datetime
from functools import cached_property
from typing import Callable

from policy.models import Action, Email

Transport = Callable[[str, dict], dict]  # (tool name, arguments) -> MCP result

ACTION_TOOLS = {  # action kind -> (tool, how to build its arguments), and the tool that undoes it
    "label": ("label_email", lambda a: {"id": a.email_id, "label": a.label}, "unlabel_email"),
    "archive": ("archive_email", lambda a: {"id": a.email_id}, "unarchive_email"),
    "mark_read": ("mark_read", lambda a: {"id": a.email_id}, "mark_unread"),
    "trash": ("trash_email", lambda a: {"id": a.email_id}, "untrash_email"),
    "draft_reply": ("create_draft", lambda a: {"reply_to": a.email_id, "body": a.body}, "delete_draft"),
    "send": ("send_email", lambda a: {"reply_to": a.email_id, "to": list(a.to), "body": a.body}, None),
    "forward": ("forward_email", lambda a: {"id": a.email_id, "to": list(a.to)}, None),
    "unsubscribe": ("unsubscribe", lambda a: {"id": a.email_id}, None),
}


def to_email(data: dict) -> Email:
    return Email(
        id=data["id"],
        thread_id=data["thread_id"],
        sender=data["from"],
        to=tuple(data["to"]),
        subject=data["subject"],
        body=data["body"],
        sent_at=datetime.fromisoformat(data["date"]),
        authenticated=data["authenticated"],
        has_unsubscribe=data["list_unsubscribe"],
    )


class MailClient:
    def __init__(self, transport: Transport):
        self.transport = transport

    def call(self, tool: str, **arguments) -> dict:
        """Calls a tool and returns its payload, with "ok" set from the result."""
        response = self.transport(tool, arguments)
        payload = json.loads(response["content"][0]["text"])
        return {**payload, "ok": not response["isError"]}

    # --- reads ---

    @cached_property
    def user_address(self) -> str:
        return self.call("get_profile")["address"]

    @cached_property
    def user_domain(self) -> str:
        return self.call("get_profile")["domain"]

    def get(self, email_id: str) -> Email:
        return to_email(self.call("get_email", id=email_id)["email"])

    def status(self, email_id: str) -> dict:
        """Labels, archived, trashed, read and draft for one email."""
        return self.call("get_email", id=email_id)

    def thread(self, thread_id: str) -> list[Email]:
        return [to_email(m) for m in self.call("list_thread", thread_id=thread_id)["messages"]]

    def latest_in_threads(self) -> list[Email]:
        return [to_email(t["last_message"]) for t in self.call("list_threads")["threads"]]

    def search(self, folder: str = "all", query: str = "", sender: str = "") -> dict:
        """{"total": n, "emails": [summaries]} for a folder: inbox, archived, trash, sent, drafts or all."""
        return self.call("search_emails", folder=folder, query=query, sender=sender)

    def contacts(self) -> set[str]:
        return set(self.call("list_contacts")["contacts"])

    # --- changes (executor only) ---

    def act(self, action: Action) -> dict:
        if action.kind == "keep":
            return {"ok": True, "status": 200}  # leaving it alone needs no call
        tool, arguments, _ = ACTION_TOOLS[action.kind]
        return self.call(tool, **arguments(action))

    def undo(self, action: Action) -> dict:
        if action.kind == "keep":
            return {"ok": True, "status": 200}
        _, arguments, undo_tool = ACTION_TOOLS[action.kind]
        if not undo_tool:
            return {"ok": False, "status": 400, "error": f"{action.kind} can't be undone"}
        args = arguments(action)
        args = {k: v for k, v in args.items() if k in ("id", "label", "reply_to")}
        return self.call(undo_tool, **args)
