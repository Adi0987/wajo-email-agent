"""Turns the agent's decisions into chat messages, and the user's replies into feedback.

Shared by the browser (`wajo.py`) and the terminal (`wajo.py try`). Presentation only:
every decision comes from the agent.
"""
import itertools
from datetime import datetime, timedelta
from typing import Optional

from agent.agent import Agent
from agent.audit import AuditLog
from agent.llm import LLM
from agent.models import Action, Email, Level
from agent.notices import Notice
from agent.profile import Profile
from agent.rates import NOTIFY_AT, SILENT_AT, cautious_rate
from agent.senders import other_party
from app.interpreter import Interpreter
from app.narrator import Narrator, describe

CATEGORY_WORDS = {"same_domain": "colleague", "contact": "someone you've emailed",
                  "newsletter": "newsletter", "unknown": "new sender"}
DONE = {"keep": "Left it in your inbox", "archive": "Archived it", "label": "Labeled it",
        "mark_read": "Marked it read", "trash": "Moved it to trash", "draft_reply": "Drafted a reply",
        "send": "Sent the reply", "forward": "Forwarded it", "unsubscribe": "Unsubscribed"}


def name_of(address: str) -> str:
    return " ".join(part.title() for part in address.split("@")[0].replace("_", ".").split(".") if part)


def times(count: float) -> str:
    return {1: "once", 2: "twice"}.get(int(count), f"{int(count)} times")


class Assistant:
    def __init__(self, agent: Agent, llm: Optional[LLM], profile: Profile, audit: AuditLog):
        self.agent, self.audit, self.profile = agent, audit, profile
        self.narrator, self.interpreter = Narrator(llm), Interpreter(llm)
        self.messages: list[dict] = []
        self.clock: Optional[datetime] = None
        self.shown: set[str] = set()     # email ids already introduced
        self._ids = itertools.count(1)
        self._log_seen = self._notices_seen = 0
        self._decisions: dict = {}       # action -> (entry, message text)
        self._open: dict = {}            # message id -> notice waiting for an answer

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
        return [self.note(f"It's now {self.clock:%a %b %d %Y}.")] + self._step()

    def answer(self, message_id: int, reply: str) -> list[dict]:
        """The user's reply to an open message, in their own words."""
        if message_id not in self._open:
            return [self.note("That one has already been answered.")]
        notice = self._open.pop(message_id)
        message = next(m for m in self.messages if m["id"] == message_id)
        message["open"], message["answer"] = False, reply or "yes"
        result = self.interpreter(reply, message["text"])
        spec = result["instead"]
        instead = Action(spec["kind"], notice.email_id, label=spec.get("label", ""), body=spec.get("body", "")) \
            if spec else None
        if instead and notice.action and instead.kind == notice.action.kind and not instead.label and not instead.body:
            instead = None                 # "archive it" when I proposed archiving is a yes
            result["decision"] = "yes"
        agreed = result["decision"] == "yes" and not instead
        if notice.kind == "ask":
            if agreed:
                self.agent.approve(notice, notice.at)
                self.audit.response(notice.email_id, "approved")
            else:
                self.agent.reject(notice, chosen=instead.kind if instead else None)
                self.audit.response(notice.email_id, f"rejected, wanted {instead.kind}" if instead else "rejected")
        elif notice.kind == "notify":
            if agreed:
                self.agent.confirm(notice)
                self.audit.response(notice.email_id, "confirmed")
            else:
                self.agent.undo(notice.action, chosen=instead.kind if instead else None)
                self.audit.response(notice.email_id, f"undone, wanted {instead.kind}" if instead else "undone")
        else:
            verdict = result["timing"] or "ok"
            self.agent.timing_feedback(notice, verdict)
            self.audit.response(notice.email_id, f"{notice.kind} timing {verdict.replace('_', ' ')}")
        new = []
        if result.get("remember"):
            self.profile.add(result["remember"])
            new.append(self.note(f"I'll remember that: {result['remember']}"))
        acknowledgement = result["acknowledgement"] or self._acknowledge(notice, agreed, instead)
        if acknowledgement:
            new.append(self.note(acknowledgement))
        if instead:
            self.agent.do_instead(instead, self.clock)
        return new + self._step()

    def tell(self, text: str) -> list[dict]:
        """A message from the user outside any question. Only facts or preferences about them are remembered."""
        self._add("user", text=text)
        result = self.interpreter.chat(text, self.profile.text())
        if result["remember"]:
            self.profile.add(result["remember"])
        return [self.note(result["reply"])]

    def waiting(self) -> set[str]:
        """Email ids with a question the user hasn't answered yet."""
        return {notice.email_id for notice in self._open.values()}

    def note(self, text: str) -> dict:
        return self._add("note", text=text)

    # --- what the agent has learned and scheduled (for Diagnostics and the session log) ---

    def learned(self) -> dict:
        """What the agent has learned from feedback: per sender, and per kind of sender."""
        agent = self.agent
        mailbox, rates = agent.mailbox, agent.rates
        category = {}
        for email in mailbox.emails.values():
            address, kind_of_sender = other_party(email, mailbox)
            category[address] = kind_of_sender
        senders = [{"who": sender, "action": kind, "approved": int(a), "rejected": int(r),
                    "level": rates.level(kind, sender, category.get(sender, "unknown")).name.title()}
                   for (kind, sender), (a, r) in rates.by_sender.items() if a or r]
        groups = [{"who": CATEGORY_WORDS.get(group, group), "action": kind, "approved": int(a), "rejected": int(r),
                   "rate": f"{cautious_rate(a, r):.0%}"}
                  for (kind, group), (a, r) in rates.by_category.items() if a or r]
        return {"senders": senders, "groups": groups}

    def timing(self) -> list[dict]:
        timing = self.agent.timing
        groups = sorted(set(timing.n) | set(timing.l))
        return [{"who": CATEGORY_WORDS.get(g, g), "follow_up": f"{timing.n[g]:.1f} days",
                 "reminder": f"{timing.l[g]:.1f} days before"} for g in groups]

    def scheduled(self) -> list[dict]:
        items = []
        for item in self.agent.scheduler.pending():
            email = item["email"]
            if item["kind"] == "follow_up":
                what = f"Follow up with {email.to[0]} on \"{email.subject}\" if no reply"
            else:
                what = f"Remind you about \"{email.subject}\" (due {item['deadline']:%b %d})"
            items.append({"what": what, "at": f"{item['at']:%a %b %d %H:%M}"})
        return items

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
            text = f"{DONE[action.kind]}." if entry["executed"] else "I didn't do that: it's no longer allowed."
            return [self._add("result", text=text)]
        email = self.agent.mailbox.get(action.email_id)
        text = self.narrator(self.agent.mailbox.user_address, email, action, level, self._why(entry))
        self._decisions[action] = (entry, text)
        self.audit.decision(entry, email, other_party(email, self.agent.mailbox)[1], self.agent.labels.get(email.id, {}))
        new = []
        if email.id not in self.shown and email.sender != self.agent.mailbox.user_address:
            self.shown.add(email.id)
            new.append(self._email_message(email))
        if level == Level.SILENT:
            new.append(self._add("silent", text=text, details=self._details(entry), about=self._about(email)))
        return new

    def _notice(self, notice: Notice) -> dict:
        email = self.agent.mailbox.get(notice.email_id)
        if notice.kind == "nudge":
            days = (notice.at - email.sent_at).days
            return self._add("nudge", notice=notice, text=f"You emailed {name_of(email.to[0])} about \"{email.subject}\" "
                             f"{days} days ago and haven't heard back. Want to follow up? Is this good timing?")
        if notice.kind == "reminder":
            due = self.agent.scheduler.deadlines[email.id]
            return self._add("reminder", notice=notice, text=f"Heads up: \"{email.subject}\" from {name_of(email.sender)} "
                             f"is due {due:%A, %b %d}. Was this reminder good timing?")
        entry, text = self._decisions[notice.action]
        open_notice = notice if notice.kind in ("ask", "notify") else None
        return self._add(notice.kind, notice=open_notice, text=text, draft=notice.action.body,
                         details=self._details(entry), about=self._about(email))

    def _about(self, email: Email) -> dict:
        _, category = other_party(email, self.agent.mailbox)
        return {"name": name_of(email.sender), "sender": email.sender, "category": CATEGORY_WORDS[category],
                "subject": email.subject or "(no subject)", "date": f"{email.sent_at:%b %d %Y}", "body": email.body[:2000]}

    def _email_message(self, email: Email) -> dict:
        _, category = other_party(email, self.agent.mailbox)
        return self._add("email", sender=email.sender, name=name_of(email.sender),
                         category=CATEGORY_WORDS[category], subject=email.subject or "(no subject)",
                         date=f"{email.sent_at:%b %d %Y}", body=email.body[:2000])

    def _why(self, entry: dict) -> str:
        """Why the agent asked, notified or went quiet, from the check that set the level."""
        checks, action, level = entry["checks"], entry["action"], entry["level"]
        if level == Level.ESCALATE:
            return "the email looks like phishing or an attempt to get you or me to send mail somewhere it shouldn't go"
        if checks["action"] == level:
            return "this would leave your mailbox and can't be undone, so I always check first"
        if checks["email"] == level:
            return "it mentions money, so I check with you or tell you"
        sender = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)[0]
        approvals, rejections = self.agent.rates.by_sender[(action.kind, sender)]
        if level == Level.SILENT:
            return f"you've okayed this {times(approvals)}" if approvals else "you always okay this for similar senders"
        if level == Level.NOTIFY:
            return f"you've okayed this {times(approvals)}" if approvals else "you usually okay this for similar senders"
        if rejections:
            return "you've said no to this before"
        if approvals:
            return f"you've okayed this {times(approvals)} so far, a few more and I'll stop asking"
        return f"this is the first time I've seen this from {name_of(sender)}, so I don't know your preference yet"

    def _details(self, entry: dict) -> dict:
        action = entry["action"]
        sender, category = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)
        rate = self.agent.rates.rate(action.kind, sender, category)
        return {**{name: level.name.title() for name, level in entry["checks"].items()},
                "rate": f"approval rate {rate:.0%} (Notify ≥{NOTIFY_AT:.0%}, Silent ≥{SILENT_AT:.0%})"}

    @staticmethod
    def _acknowledge(notice: Notice, agreed: bool, instead: Optional[Action]) -> str:
        if instead:
            return f"OK, I'll {describe(instead)} instead, and remember that for emails like this."
        if agreed:
            return ""
        return "Undone." if notice.kind == "notify" else "OK, I won't."

    def _add(self, kind: str, notice: Optional[Notice] = None, **fields) -> dict:
        message = {"id": next(self._ids), "kind": kind, "open": notice is not None, **fields}
        if notice:
            self._open[message["id"]] = notice
        self.messages.append(message)
        return message
