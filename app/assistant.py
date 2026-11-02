"""Turns the agent's decisions into plain-language messages, and the user's replies into feedback.

Shared by the terminal (`wajo.py try`) and the web page (`wajo.py ui`). Presentation only:
every decision comes from the agent.
"""
import itertools
from datetime import datetime, timedelta
from typing import Optional

from agent.agent import Agent
from agent.audit import AuditLog
from agent.checks import ACTIONS
from agent.models import Action, Email, Level
from agent.notices import Notice
from agent.rates import NOTIFY_AT, SILENT_AT
from agent.senders import other_party
from app.narrator import Narrator, describe

CATEGORY_WORDS = {"same_domain": "colleague", "contact": "someone you've emailed",
                  "newsletter": "newsletter", "unknown": "new sender"}
DONE = {"keep": "Left it in your inbox", "archive": "Archived it", "label": "Labeled it",
        "mark_read": "Marked it read", "trash": "Moved it to trash", "draft_reply": "Drafted a reply",
        "send": "Sent the reply", "forward": "Forwarded it", "unsubscribe": "Unsubscribed"}
ALIASES = {"reply": "draft_reply", "leave": "keep", "inbox": "keep", "delete": "trash", "read": "mark_read"}
CHOICES = "archive, label <name>, trash, keep, reply"


def name_of(address: str) -> str:
    return " ".join(part.title() for part in address.split("@")[0].replace("_", ".").split(".") if part)


def times(count: float) -> str:
    return {1: "once", 2: "twice"}.get(int(count), f"{int(count)} times")


class Assistant:
    def __init__(self, agent: Agent, narrator: Narrator, audit: AuditLog):
        self.agent, self.narrator, self.audit = agent, narrator, audit
        self.messages: list[dict] = []
        self.clock: Optional[datetime] = None
        self._ids = itertools.count(1)
        self._log_seen = self._notices_seen = 0
        self._decisions: dict = {}       # action -> (entry, reason)
        self._open: dict = {}            # message id -> notice waiting for an answer
        self.shown: set[str] = set()     # email ids already introduced

    # --- input from the user's side ---

    def deliver(self, email: Email) -> list[dict]:
        """A new email arrives."""
        self.clock = max(self.clock or email.sent_at, email.sent_at)
        self.agent.mailbox.receive(email)
        self.agent.on_new_mail(email)
        return self._step()

    def wait(self, days: float) -> list[dict]:
        """Time passes; follow-ups and reminders may fire."""
        self.clock = (self.clock or datetime.now()) + timedelta(days=days)
        return [self._add("note", text=f"It's now {self.clock:%a %b %d %Y}.")] + self._step()

    def answer(self, message_id: int, reply: str) -> list[dict]:
        """reply: yes / no / fine / undo / ok / too_early / too_late, or an action like "label reading"."""
        notice = self._open.pop(message_id)
        message = next(m for m in self.messages if m["id"] == message_id)
        message["open"], message["answer"] = False, reply
        new = []
        if notice.kind == "ask":
            if reply == "yes":
                self.agent.approve(notice, notice.at)
                self.audit.response(notice.email_id, "approved")
            else:
                chosen = self._chosen(reply, notice.email_id, new)
                self.agent.reject(notice, chosen=chosen.kind if chosen else None)
                self.audit.response(notice.email_id, f"rejected, wanted {chosen.kind}" if chosen else "rejected")
                new.append(self._add("note", text=f"Got it. {self._remember(chosen)}".strip()))
        elif notice.kind == "notify":
            if reply == "fine":
                self.agent.confirm(notice)
                self.audit.response(notice.email_id, "confirmed")
            else:
                chosen = None if reply == "undo" else self._chosen(reply, notice.email_id, new)
                self.agent.undo(notice.action, chosen=chosen.kind if chosen else None)
                self.audit.response(notice.email_id, f"undone, wanted {chosen.kind}" if chosen else "undone")
                new.append(self._add("note", text=f"Undone. {self._remember(chosen)}".strip()))
        else:
            self.agent.timing_feedback(notice, reply)
            self.audit.response(notice.email_id, f"{notice.kind} timing {reply.replace('_', ' ')}")
        return new + self._step()

    def note(self, text: str) -> dict:
        return self._add("note", text=text)

    # --- turning agent output into messages ---

    def _step(self) -> list[dict]:
        self.agent.tick(self.clock)
        new = []
        while self._log_seen < len(self.agent.executor.log) or self._notices_seen < len(self.agent.notices):
            for entry in self.agent.executor.log[self._log_seen:]:
                self._log_seen += 1
                new += self._decision(entry)
            for notice in self.agent.notices[self._notices_seen:]:
                self._notices_seen += 1
                new.append(self._notice(notice))
        return new

    def _decision(self, entry: dict) -> list[dict]:
        action, level = entry["action"], entry["level"]
        if entry["approved"]:
            text = f"{DONE[action.kind]}." if entry["executed"] else "I didn't do it: it changed or is no longer allowed."
            return [self._add("result", text=text)]
        email = self.agent.mailbox.get(action.email_id)
        summary, reason = self.narrator(self.agent.mailbox.user_address, email, action, level)
        self._decisions[action] = (entry, reason)
        self.audit.decision(entry, email, other_party(email, self.agent.mailbox)[1], self.agent.labels.get(email.id, {}))
        new = []
        if email.id not in self.shown and email.sender != self.agent.mailbox.user_address:
            self.shown.add(email.id)
            new.append(self._email_message(email, summary))
        if level == Level.SILENT:
            new.append(self._add("silent", text=f"{DONE[action.kind]} quietly.", reason=reason,
                                 details=self._details(entry)))
        return new

    def _notice(self, notice: Notice) -> dict:
        email = self.agent.mailbox.get(notice.email_id)
        if notice.kind in ("nudge", "reminder"):
            if notice.kind == "nudge":
                text = f"No reply from {name_of(email.to[0])} to \"{email.subject}\" after {(notice.at - email.sent_at).days} days."
            else:
                text = f"Reminder: \"{email.subject}\" is due {self.agent.scheduler.deadlines[email.id]:%a %b %d}."
            return self._add(notice.kind, text=text, question="Good timing?", notice=notice)
        entry, reason = self._decisions[notice.action]
        common = dict(reason=reason, why=self._why(entry), details=self._details(entry))
        if notice.kind == "ask":
            plan = "I'd leave this one for you." if notice.action.kind == "keep" else f"I'd like to {describe(notice.action)}."
            return self._add("ask", text=plan, draft=notice.action.body, question="OK?", notice=notice, **common)
        if notice.kind == "notify":
            return self._add("notify", text=f"{DONE[notice.action.kind]}.", question="All good?", notice=notice, **common)
        return self._add("escalate", text="I'm not touching this one.", reason=reason, details=self._details(entry),
                         why="It looks like an attempt to manipulate me or phish you. Worth checking with the sender directly.")

    def _email_message(self, email: Email, summary: str) -> dict:
        _, category = other_party(email, self.agent.mailbox)
        return self._add("email", sender=email.sender, name=name_of(email.sender),
                         category=CATEGORY_WORDS[category], subject=email.subject or "(no subject)",
                         date=f"{email.sent_at:%b %d %Y}", summary=summary, body=email.body[:2000])

    def _why(self, entry: dict) -> str:
        """Why the agent asked or notified, from the check that set the level."""
        checks, action, level = entry["checks"], entry["action"], entry["level"]
        if checks["action"] == level:
            return "This would leave your mailbox and can't be undone, so I always check first."
        if checks["email"] == level:
            return f"It mentions money, so I'm {'checking with you' if level == Level.ASK else 'letting you know'}."
        sender = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)[0]
        approvals, rejections = self.agent.rates.by_sender[(action.kind, sender)]
        if level == Level.NOTIFY:
            return f"You've okayed this {times(approvals)}, so I went ahead." if approvals \
                else "You usually okay this for similar senders, so I went ahead."
        if rejections:
            return "You've said no to this before, so I'm checking."
        if approvals:
            return f"You've okayed this {times(approvals)} so far. A few more and I'll stop asking."
        return f"I haven't learned how you handle this from {name_of(sender)} yet."

    def _details(self, entry: dict) -> dict:
        action = entry["action"]
        sender, category = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)
        rate = self.agent.rates.rate(action.kind, sender, category)
        return {**{name: level.name.title() for name, level in entry["checks"].items()},
                "rate": f"approval rate {rate:.0%} (Notify ≥{NOTIFY_AT:.0%}, Silent ≥{SILENT_AT:.0%})"}

    def _chosen(self, reply: str, email_id: str, new: list) -> Optional[Action]:
        """The action the user typed, e.g. "trash" or "label to read", or None."""
        word, _, rest = reply.strip().lower().partition(" ")
        kind = ALIASES.get(word, word)
        if kind in ACTIONS:
            label = rest.replace("with", "", 1).strip().strip("'\"") if kind == "label" else ""
            return Action(kind, email_id, label=label)
        if reply not in ("no", "undo"):
            new.append(self._add("note", text=f"I didn't understand \"{reply}\", so I'm taking it as a no. "
                                              f"I understand: {CHOICES}."))
        return None

    def _remember(self, chosen: Optional[Action]) -> str:
        return f"I'll remember you'd rather {describe(chosen)} for emails like this." if chosen else ""

    def _add(self, kind: str, notice: Optional[Notice] = None, **fields) -> dict:
        message = {"id": next(self._ids), "kind": kind, "open": notice is not None, **fields}
        if notice:
            self._open[message["id"]] = notice
        self.messages.append(message)
        return message
