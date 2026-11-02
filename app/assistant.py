"""The conversation between the user and Wajo: turns agent decisions into chat messages,
and every user message into actions in the (simulated) mailbox.

Shared by the browser (`wajo.py`) and the terminal (`wajo.py try`). Triage decisions come from the
agent; replies, sends and reminders the user asks for go through the agent's executor, so the safety
checks still apply. What Wajo says back is built from what actually happened.
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
from app.drafter import Drafter
from app.interpreter import Interpreter
from app.narrator import Narrator, describe

CATEGORY_WORDS = {"same_domain": "colleague", "contact": "someone you've emailed",
                  "newsletter": "newsletter", "unknown": "new sender"}
DONE = {"keep": "Left it in your inbox", "archive": "Archived it", "label": "Labeled it",
        "mark_read": "Marked it read", "trash": "Moved it to trash", "draft_reply": "Saved the draft",
        "send": "Sent the reply", "forward": "Forwarded it", "unsubscribe": "Unsubscribed"}


def name_of(address: str) -> str:
    return " ".join(part.title() for part in address.split("@")[0].replace("_", ".").split(".") if part)


def times(count: float) -> str:
    return {1: "once", 2: "twice"}.get(int(count), f"{int(count)} times")


class Assistant:
    def __init__(self, agent: Agent, llm: Optional[LLM], profile: Profile, audit: AuditLog):
        self.agent, self.audit, self.profile = agent, audit, profile
        self.narrator, self.interpreter, self.drafter = Narrator(llm), Interpreter(llm), Drafter(llm)
        self.messages: list[dict] = []
        self.clock: Optional[datetime] = None
        self.focus: Optional[str] = None     # the email the conversation is about
        self.shown: set[str] = set()         # email ids already introduced
        self._ids = itertools.count(1)
        self._log_seen = self._notices_seen = 0
        self._decisions: dict = {}           # action -> (entry, message text)
        self._custom: dict = {}              # action -> what Wajo says about it (for actions the user asked for)
        self._open: dict = {}                # message id -> notice waiting for an answer

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

    def say(self, text: str) -> list[dict]:
        """Anything the user writes: an answer, an instruction, a question, or something about themselves."""
        self._add("user", text=text or "yes")
        question_id = self._question()
        notice = self._open.get(question_id)
        result = self.interpreter.turn(text, self._context(), has_question=notice is not None)
        outcome = []                          # sentences describing what actually happened
        acted = False                         # whether anything happened at all (some actions speak for themselves)

        if notice and self._resolves(notice, result):
            outcome += self._resolve(question_id, notice, result)
            acted = True
        email_id = (notice.email_id if notice else None) or self.focus
        if result["reply"] and email_id:
            outcome.append(self._draft(email_id, result["reply"]["instructions"]))
            acted = True
        elif result["send"] and email_id and not (notice and notice.kind == "ask" and notice.action.kind == "send"):
            outcome.append(self._send_draft(email_id))
            acted = True
        if result["remind_in_days"] and email_id:
            when = self.clock + timedelta(days=result["remind_in_days"])
            self.agent.remind(email_id, when)
            outcome.append(f"I'll remind you about it on {when:%a %b %d}.")
        if result["remember"]:
            self.profile.add(result["remember"])
            outcome.append(f"I'll remember: {result['remember'].rstrip('.')}.")

        new = [self.note(" ".join(o for o in outcome if o))] if any(outcome) else []
        draft = self.agent.mailbox.drafts.get(email_id) if email_id else None
        if result["question"] and "draft" in text.lower() and draft:
            new.append(self.note(f"Here's the current draft:\n\n{draft}"))      # straight from the mailbox
        elif result["question"] or not (acted or any(outcome)):
            new.append(self.note(self.interpreter.answer(text, self._context())))
        return new + self._step()

    def note(self, text: str) -> dict:
        return self._add("note", text=text)

    def waiting(self) -> set[str]:
        """Email ids with a question the user hasn't answered yet."""
        return {notice.email_id for notice in self._open.values()}

    # --- acting on what the user said ---

    def _question(self) -> Optional[int]:
        """The open question the user is most likely answering: the newest one."""
        return max(self._open) if self._open else None

    @staticmethod
    def _resolves(notice: Notice, result: dict) -> bool:
        if notice.kind in ("nudge", "reminder"):
            return bool(result["answer"] or result["timing"])
        return bool(result["answer"] or result["instead"] or result["reply"] or result["send"])

    def _resolve(self, message_id: int, notice: Notice, result: dict) -> list[str]:
        """Applies the user's answer to an open question. Returns what happened, in words."""
        del self._open[message_id]
        next(m for m in self.messages if m["id"] == message_id)["open"] = False
        if notice.kind in ("nudge", "reminder"):
            verdict = result["timing"] or "ok"
            self.agent.timing_feedback(notice, verdict)
            self.audit.response(notice.email_id, f"{notice.kind} timing {verdict.replace('_', ' ')}")
            return []
        spec = result["instead"]
        instead = Action(spec["kind"], notice.email_id, label=spec.get("label", ""), to=tuple(spec.get("to") or ())) \
            if spec else None
        if instead and instead.kind == notice.action.kind and instead.label == notice.action.label:
            instead = None                     # "archive it" when I proposed archiving is a yes
        # asking for a reply is an extra step, not a vote against the triage decision
        agreed = not instead and (result["answer"] == "yes" or (result["answer"] is None and
                                                                (result["reply"] or result["send"])))
        if notice.kind == "ask":
            if agreed:
                self.agent.approve(notice, self.clock)
                self.audit.response(notice.email_id, "approved")
                return []
            self.agent.reject(notice, chosen=instead.kind if instead else None)
            self.audit.response(notice.email_id, f"rejected, wanted {instead.kind}" if instead else "rejected")
            if not instead:
                return [f"OK, I won't {describe(notice.action)}." if notice.action.kind != "keep" else ""]
        else:                                  # notify
            if agreed:
                self.agent.confirm(notice)
                self.audit.response(notice.email_id, "confirmed")
                return []
            self.agent.undo(notice.action, chosen=instead.kind if instead else None)
            self.audit.response(notice.email_id, f"undone, wanted {instead.kind}" if instead else "undone")
            if not instead:
                return ["Undone."]
        if self.agent.do_instead(instead, self.clock):
            return [f"OK, I'll {describe(instead)} instead."]
        return [f"I can't {describe(instead)} for this email: the safety checks don't allow it."]

    def _draft(self, email_id: str, instructions: str) -> str:
        """Writes the reply the user asked for, saves it as a draft, and asks before sending it."""
        email = self.agent.mailbox.get(email_id)
        body = self.drafter(self.agent.mailbox.user_address, email, instructions, self.profile.text())
        if not self.agent.do_instead(Action("draft_reply", email_id, body=body), self.clock):
            return "I can't write a reply to this email: the safety checks don't allow it."
        send = Action("send", email_id, to=(email.sender,), body=body)
        self._custom[send] = f"Here's a draft to {name_of(email.sender)}. Want me to send it?"
        self.agent.executor.handle(send, self.clock)    # sending always needs your OK
        return ""

    def _send_draft(self, email_id: str) -> str:
        body = self.agent.mailbox.drafts.get(email_id)
        if not body:
            return "There's no draft for this email yet. Tell me what to say and I'll write one."
        email = self.agent.mailbox.get(email_id)
        if self.agent.executor.run_requested(Action("send", email_id, to=(email.sender,), body=body), self.clock):
            return ""
        return "I can't send this one: the safety checks don't allow it."

    def _context(self) -> str:
        """What the interpreter needs to understand the user: open question, focused email, its draft, recent chat."""
        parts = []
        question_id = self._question()
        if question_id:
            parts.append(f"Your open question: {next(m for m in self.messages if m['id'] == question_id)['text']}")
        if self.focus:
            email = self.agent.mailbox.get(self.focus)
            parts.append(f"The email being discussed: from {email.sender}, subject \"{email.subject}\"\n"
                         f"{' '.join(email.body.split())[:1200]}")
            draft = self.agent.mailbox.drafts.get(self.focus)
            parts.append(f"Current draft:\n{draft}" if draft else "Current draft: none")
        scheduled = self.scheduled()
        if scheduled:
            parts.append("Scheduled: " + "; ".join(f"{s['at']}: {s['what']}" for s in scheduled))
        parts.append("What the user has told you about themselves:\n" + (self.profile.text() or "(nothing yet)"))
        recent = [m for m in self.messages if m["kind"] in ("user", "note", "ask", "notify", "silent", "escalate",
                                                             "nudge", "reminder", "remind_me")][-8:]
        parts.append("Recent conversation:\n" + "\n".join(
            f"{'User' if m['kind'] == 'user' else 'Wajo'}: {m['text']}" for m in recent))
        return "\n\n".join(parts)

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
            elif item["kind"] == "requested":
                what = f"Remind you about \"{email.subject}\" (you asked)"
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
            if action.kind == "draft_reply":
                return []                      # the draft is shown with the question that asks to send it
            text = f"{DONE[action.kind]}." if entry["executed"] else "I didn't do that: it's no longer allowed."
            return [self._add("result", text=text)]
        email = self.agent.mailbox.get(action.email_id)
        self.focus = email.id
        text = self._custom.pop(action, None) or \
            self.narrator(self.agent.mailbox.user_address, email, action, level, self._why(entry))
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
        self.focus = email.id
        if notice.kind == "nudge":
            days = (notice.at - email.sent_at).days
            return self._add("nudge", notice=notice, about=self._about(email),
                             text=f"You emailed {name_of(email.to[0])} about \"{email.subject}\" {days} days ago and "
                                  "haven't heard back. Want me to draft a follow-up? And was this good timing?")
        if notice.kind == "remind_me":
            return self._add("remind_me", text=f"Here's the reminder you asked for: \"{email.subject}\" "
                             f"from {name_of(email.sender)}.", about=self._about(email))
        if notice.kind == "reminder":
            due = self.agent.scheduler.deadlines[email.id]
            return self._add("reminder", notice=notice, about=self._about(email),
                             text=f"Heads up: \"{email.subject}\" from {name_of(email.sender)} is due {due:%A, %b %d}. "
                                  "Was this reminder good timing?")
        entry, text = self._decisions[notice.action]
        open_notice = notice if notice.kind in ("ask", "notify") else None
        return self._add(notice.kind, notice=open_notice, text=text, draft=notice.action.body,
                         details=self._details(entry), about=self._about(email))

    def _about(self, email: Email) -> dict:
        _, category = other_party(email, self.agent.mailbox)
        return {"name": name_of(email.sender), "sender": email.sender, "category": CATEGORY_WORDS[category],
                "subject": email.subject or "(no subject)", "date": f"{email.sent_at:%b %d %Y}", "body": email.body[:2000]}

    def _email_message(self, email: Email) -> dict:
        return self._add("email", **self._about(email))

    def _why(self, entry: dict) -> str:
        """Why the agent chose this level, when there's a reason worth saying. Empty when it simply hasn't
        learned the user's preference yet: then it just asks."""
        checks, action, level = entry["checks"], entry["action"], entry["level"]
        if level == Level.ESCALATE:
            return "the email looks like phishing or an attempt to get mail sent somewhere it shouldn't go"
        if checks["action"] == level:
            return "this would leave your mailbox and can't be undone, so I always check first"
        if checks["email"] == level:
            return "it mentions money, so I check with you or tell you"
        sender = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)[0]
        approvals, _ = self.agent.rates.by_sender[(action.kind, sender)]
        if level in (Level.SILENT, Level.NOTIFY):
            return f"you've okayed this {times(approvals)}" if approvals else "you usually okay this for similar senders"
        return ""

    def _details(self, entry: dict) -> dict:
        action = entry["action"]
        sender, category = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)
        rate = self.agent.rates.rate(action.kind, sender, category)
        return {**{name: level.name.title() for name, level in entry["checks"].items()},
                "rate": f"approval rate {rate:.0%} (Notify ≥{NOTIFY_AT:.0%}, Silent ≥{SILENT_AT:.0%})"}

    def _add(self, kind: str, notice: Optional[Notice] = None, **fields) -> dict:
        message = {"id": next(self._ids), "kind": kind, "open": notice is not None, **fields}
        if notice:
            self._open[message["id"]] = notice
        self.messages.append(message)
        return message
