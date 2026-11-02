"""`python3 wajo.py try`: you are the user. Emails arrive one at a time, the agent decides, you answer.

With enron-email-dataset.zip in the folder: random emails from a real Enron inbox, with DeepSeek (needs LLM_API_KEY).
Without it, or with --offline: the synthetic inbox and the offline stand-in LLM (no key needed).
"""
from datetime import datetime
from pathlib import Path

from agent.agent import Agent
from agent.audit import AuditLog
from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Action, Email, Level
from agent.notices import Notice
from agent.proposer import Proposer
from agent.rates import NOTIFY_AT, SILENT_AT
from agent.checks import ACTIONS
from agent.senders import other_party
from eval import enron
from eval.inbox import USER, build_inbox
from eval.llm_steps import llm_steps
from eval.narrator import Narrator, describe
from eval.style import BLUE, BOLD, CYAN, DIM, GREEN, RED, YELLOW, level_word, paint

ENRON_ZIP = "enron-email-dataset.zip"
CATEGORY_WORDS = {"same_domain": "colleague", "contact": "someone you've emailed",
                  "newsletter": "newsletter", "unknown": "new sender"}
DONE = {"keep": "Left it in your inbox", "archive": "Archived it", "label": "Labeled it",
        "mark_read": "Marked it read", "trash": "Moved it to trash", "draft_reply": "Drafted a reply",
        "send": "Sent the reply", "forward": "Forwarded it", "unsubscribe": "Unsubscribed"}
ALIASES = {"reply": "draft_reply", "leave": "keep", "inbox": "keep", "delete": "trash", "read": "mark_read"}
CHOICES = "archive, label, trash, keep, reply"


def name_of(address: str) -> str:
    return " ".join(part.title() for part in address.split("@")[0].replace("_", ".").split(".") if part)


def setup(persona: str, count: int, offline: bool) -> tuple[Agent, list[Email], Narrator]:
    """The agent, the emails to feed it, and the narrator that explains decisions."""
    if not offline and Path(ENRON_ZIP).exists():
        print(f"Picking {count} random emails from {persona}'s inbox...")
        user, feed = enron.sample_inbox(ENRON_ZIP, persona, count)
        llm = LLM(cache_path=".llm_cache_local.json")   # keeps these emails out of the eval cache
        propose, classify, narrator = Proposer(llm), Classifier(llm), Narrator(llm)
        history = []
    else:
        cases = build_inbox(seed=7)
        user, history = USER, [c.email for c in cases if not c.incoming]
        feed = [c.email for c in cases if c.incoming][:count]
        propose, classify = llm_steps("stub", cases, seed=7)
        narrator = Narrator(None)
    print(paint("\nHi, I'm your email assistant. ", BOLD)
          + f"{len(feed)} emails are coming in. I'll ask before doing things until I learn how you like them handled.")
    mailbox = Mailbox(user)
    for email in history:       # synthetic inbox only: the user's past mail, so contacts exist
        mailbox.receive(email)
    return Agent(mailbox, propose, classify), feed, narrator


class Session:
    def __init__(self, agent: Agent, feed: list[Email], audit: AuditLog, narrator: Narrator, details: bool):
        self.agent, self.feed, self.audit, self.narrator, self.details = agent, feed, audit, narrator, details
        self.notices_seen = self.log_seen = 0
        self.decisions: dict = {}         # action -> its decision entry
        self.reasons: dict = {}           # action -> reason sentence
        self.summarized: set[str] = set()

    def run(self) -> None:
        for number, email in enumerate(self.feed, 1):
            _, category = other_party(email, self.agent.mailbox)
            print("\n" + paint(f"━━━ {number}/{len(self.feed)} · {name_of(email.sender)} ", BLUE, BOLD)
                  + paint(f"({CATEGORY_WORDS[category]}, {email.sender}) · {email.sent_at:%b %d %Y}", DIM))
            print(f"    \"{paint(email.subject or '(no subject)', BOLD)}\"")
            self.agent.mailbox.receive(email)
            self.agent.on_new_mail(email)
            self.agent.tick(email.sent_at)
            self.show_updates()
            if input(paint("\n  [enter] next email · q quit ", DIM)).strip().lower() == "q":
                break
        print("\n" + paint("Session summary", BOLD) + "\n" + self.audit.summary())

    def show_updates(self) -> None:
        """New decisions and notices, in order, until nothing new is left."""
        while self.log_seen < len(self.agent.executor.log) or self.notices_seen < len(self.agent.notices):
            for entry in self.agent.executor.log[self.log_seen:]:
                self.log_seen += 1
                if entry["approved"]:
                    if entry["executed"]:
                        print(paint(f"  ✔ {DONE[entry['action'].kind]}.", GREEN))
                    else:
                        print(paint("  ✖ I didn't do it: it changed or is no longer allowed.", RED))
                else:
                    self.record(entry)
            for notice in self.agent.notices[self.notices_seen:]:
                self.notices_seen += 1
                self.answer(notice)

    def record(self, entry: dict) -> None:
        """Summarizes the email (once), works out the reason, and handles Silent decisions."""
        action, level = entry["action"], entry["level"]
        email = self.agent.mailbox.get(action.email_id)
        summary, reason = self.narrator(self.agent.mailbox.user_address, email, action, level)
        if email.id not in self.summarized and email.sender != self.agent.mailbox.user_address:
            self.summarized.add(email.id)
            print(f"    {summary}")
        self.decisions[action], self.reasons[action] = entry, reason
        self.audit.decision(entry, email, other_party(email, self.agent.mailbox)[1], self.agent.labels.get(email.id, {}))
        if level == Level.SILENT:
            print(paint(f"\n  ✔ {DONE[action.kind]} quietly. ", GREEN) + reason)
            self.show_details(entry)

    def why(self, entry: dict) -> str:
        """Why the agent asked or notified, from the check that set the level."""
        checks, action, level = entry["checks"], entry["action"], entry["level"]
        if checks["action"] == level:
            return "This would leave your mailbox and can't be undone, so I always check first."
        if checks["email"] == level:
            return "It involves money, so I'm checking with you." if level == Level.ASK \
                else "It involves money, so I'm letting you know."
        sender = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)[0]
        approvals, rejections = self.agent.rates.by_sender[(action.kind, sender)]
        if level == Level.NOTIFY:
            return f"You've okayed this {int(approvals)} times, so I went ahead." if approvals \
                else "You usually okay this for similar senders, so I went ahead."
        if rejections:
            return "You've said no to this before, so I'm checking."
        if approvals:
            return f"You've okayed this {int(approvals)} time{'s' if approvals > 1 else ''} so far. A few more and I'll stop asking."
        return f"I haven't learned how you handle this from {name_of(sender)} yet."

    def show_details(self, entry: dict) -> None:
        if not self.details:
            return
        action = entry["action"]
        sender, category = other_party(self.agent.mailbox.get(action.email_id), self.agent.mailbox)
        rate = self.agent.rates.rate(action.kind, sender, category)
        for name, allowed in entry["checks"].items():
            extra = f"  approval rate {rate:.0%} (Notify ≥{NOTIFY_AT:.0%}, Silent ≥{SILENT_AT:.0%})" if name == "learned" else ""
            print(paint(f"      {name:<8}", DIM) + level_word(allowed) + paint(extra, DIM))

    def answer(self, notice: Notice) -> None:
        agent, kind = self.agent, notice.kind
        entry = self.decisions.get(notice.action) if notice.action else None
        reason = self.reasons.get(notice.action, "")
        if kind == "ask":
            plan = "I'd leave this one for you." if notice.action.kind == "keep" else f"I'd like to {describe(notice.action)}."
            print(paint(f"\n  ? {plan} ", BOLD, YELLOW) + reason)
            print(paint(f"    {self.why(entry)}", DIM))
            if notice.action.body:
                print(paint("    Draft: ", DIM) + notice.action.body[:300])
            self.show_details(entry)
            answer = self.ask_user(f"    OK? [y] yes · [n] no · or tell me what to do ({CHOICES}) ")
            if answer in ("", "y", "yes"):
                agent.approve(notice, notice.at)
                response = "approved"
            else:
                chosen = self.chosen(answer)
                agent.reject(notice, chosen=chosen)
                response = f"rejected, wanted {chosen}" if chosen else "rejected"
                print(paint(f"  Got it. {self.remember(chosen)}", DIM))
        elif kind == "notify":
            print(paint(f"\n  ✔ {DONE[notice.action.kind]}. ", CYAN) + reason)
            print(paint(f"    {self.why(entry)}", DIM))
            self.show_details(entry)
            answer = self.ask_user(f"    [enter] fine · [u] undo · or tell me what to do instead ({CHOICES}) ")
            if answer == "":
                agent.confirm(notice)
                response = "confirmed"
            else:
                chosen = None if answer == "u" else self.chosen(answer)
                agent.undo(notice.action, chosen=chosen)
                response = f"undone, wanted {chosen}" if chosen else "undone"
                print(paint(f"  ↶ Undone. {self.remember(chosen)}", YELLOW))
        elif kind == "escalate":
            print(paint("\n  ⚠ I'm not touching this one. ", BOLD, RED) + reason)
            print(paint("    It looks like an attempt to manipulate me or phish you. Worth checking with the sender directly.", DIM))
            self.show_details(entry)
            response = "escalated"
        else:
            email = agent.mailbox.get(notice.email_id)
            if kind == "nudge":
                days = (notice.at - email.sent_at).days
                print(paint(f"\n  ⏰ No reply from {name_of(email.to[0])} to \"{email.subject}\" after {days} days.", BOLD, BLUE))
                question = "    Good time to follow up? [enter] yes · [e] too early · [l] too late "
            else:
                due = agent.scheduler.deadlines[notice.email_id]
                print(paint(f"\n  ⏰ Reminder: \"{email.subject}\" is due {due:%a %b %d}.", BOLD, BLUE))
                question = "    Good timing for this reminder? [enter] yes · [e] too early · [l] too late "
            verdict = {"e": "too_early", "l": "too_late"}.get(self.ask_user(question), "ok")
            agent.timing_feedback(notice, verdict)
            response = f"{kind} timing {verdict.replace('_', ' ')}"
        self.audit.response(notice.email_id, response)

    def remember(self, chosen) -> str:
        return f"I'll remember you'd rather {describe(Action(chosen, ''))} for emails like this." if chosen else ""

    def ask_user(self, question: str) -> str:
        return input(paint(question, DIM)).strip().lower()

    def chosen(self, answer: str):
        """The action the user typed, or None if it isn't one."""
        kind = ALIASES.get(answer, answer)
        if kind in ACTIONS:
            return kind
        if answer not in ("n", "no", "u"):
            print(paint(f"  I don't know \"{answer}\", so I'll just take that as a no.", DIM))
        return None


def try_agent(persona: str, count: int, offline: bool, details: bool = False) -> None:
    agent, feed, narrator = setup(persona, count, offline)
    Session(agent, feed, AuditLog(f"runs/audit_{datetime.now():%Y%m%d_%H%M%S}.csv"), narrator, details).run()
