"""`python3 wajo.py try`: you are the user. Emails arrive one at a time, the agent decides, you answer.

With enron-email-dataset.zip in the folder: a real Enron inbox, with DeepSeek (needs LLM_API_KEY).
Without it, or with --offline: the synthetic inbox and the offline stand-in LLM (no key needed).
"""
from datetime import datetime
from pathlib import Path

from agent.agent import Agent
from agent.audit import AuditLog
from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Email, Level
from agent.notices import Notice
from agent.proposer import Proposer
from agent.rates import NOTIFY_AT, SILENT_AT
from agent.senders import other_party
from eval import enron
from eval.inbox import USER, build_inbox
from eval.llm_steps import llm_steps

ENRON_ZIP = "enron-email-dataset.zip"
ACTION_REASON = {Level.SILENT: "safe to do alone", Level.ASK: "leaves the mailbox or can't be undone"}
EMAIL_REASON = {Level.SILENT: "nothing risky", Level.NOTIFY: "involves money",
                Level.ASK: "involves money", Level.ESCALATE: "looks like prompt injection"}


def setup(persona: str, count: int, offline: bool) -> tuple[Agent, list[Email]]:
    """The agent and the emails to feed it."""
    if not offline and Path(ENRON_ZIP).exists():
        print(f"Loading {persona}'s mail from {ENRON_ZIP}...")
        user, history, feed = enron.load(ENRON_ZIP, persona, count)
        llm = LLM(cache_path=".llm_cache_local.json")   # keeps these emails out of the eval cache
        propose, classify = Proposer(llm), Classifier(llm)
        print(f"You are {user}. {len(history)} sent emails loaded as history.")
    else:
        cases = build_inbox(seed=7)
        user, history = USER, [c.email for c in cases if not c.incoming]
        feed = [c.email for c in cases if c.incoming][:count]
        propose, classify = llm_steps("stub", cases, seed=7)
        print(f"Offline: synthetic inbox, stand-in LLM. You are {user}.")
    mailbox = Mailbox(user)
    for email in history:       # past sent mail: makes contacts, never processed
        mailbox.receive(email)
    return Agent(mailbox, propose, classify), feed


class Session:
    def __init__(self, agent: Agent, feed: list[Email], audit: AuditLog):
        self.agent, self.feed, self.audit = agent, feed, audit
        self.notices_seen = self.log_seen = 0

    def run(self) -> None:
        for number, email in enumerate(self.feed, 1):
            preview = " ".join(email.body.split())[:240]
            print(f"\n─── Email {number}/{len(self.feed)} · {email.sent_at:%b %d %Y} · from {email.sender}\n"
                  f"    \"{email.subject}\"\n    {preview}")
            self.agent.mailbox.receive(email)
            self.agent.on_new_mail(email)
            self.agent.tick(email.sent_at)
            self.show_decisions()
            if input("\n[enter] next email · q quit: ").strip().lower() == "q":
                break
        print("\n" + self.audit.summary())

    def show_decisions(self) -> None:
        """Explains each new decision, then asks the user anything the agent needs."""
        while self.log_seen < len(self.agent.executor.log) or self.notices_seen < len(self.agent.notices):
            for entry in self.agent.executor.log[self.log_seen:]:
                self.log_seen += 1
                if entry["approved"]:
                    print(f"    Done: {entry['action'].kind}" if entry["executed"] else "    Not run: changed or no longer allowed")
                else:
                    self.explain(entry)
            for notice in self.agent.notices[self.notices_seen:]:
                self.notices_seen += 1
                self.answer(notice)

    def explain(self, entry: dict) -> None:
        action, checks = entry["action"], entry["checks"]
        email = self.agent.mailbox.get(action.email_id)
        sender, category = other_party(email, self.agent.mailbox)
        rate = self.agent.rates.rate(action.kind, sender, category)
        target = f" to {', '.join(action.to)}" if action.to else ""
        print(f"\n    Agent wants to: {action.kind}{target}")
        print(f"    Why {entry['level'].name}: action {ACTION_REASON[checks['action']]} · "
              f"email {EMAIL_REASON[checks['email']]} · your approval rate {rate:.0%} "
              f"(Notify at {NOTIFY_AT:.0%}, Silent at {SILENT_AT:.0%})")
        if entry["level"] == Level.SILENT:
            print(f"    Done silently: {action.kind}")
        self.audit.decision(entry, email, category, self.agent.labels.get(email.id, {}))

    def answer(self, notice: Notice) -> None:
        agent, kind = self.agent, notice.kind
        if kind == "ask":
            answer = input(f"    Allow {notice.action.kind}? [y]es · [n]o · or type the action you want "
                           f"(keep, archive, label, trash, draft_reply): ").strip().lower()
            if answer in ("", "y", "yes"):
                agent.approve(notice, notice.at)
                response = "approved"
            else:
                chosen = None if answer in ("n", "no") else answer
                agent.reject(notice, chosen=chosen)
                response = f"rejected, wanted {chosen}" if chosen else "rejected"
        elif kind == "notify":
            if input(f"    Did {notice.action.kind}. [enter] fine · [u]ndo: ").strip().lower() == "u":
                agent.undo(notice.action)
                response = "undone"
            else:
                agent.confirm(notice)
                response = "confirmed"
        elif kind == "escalate":
            print("    ESCALATED: suspected injection or phishing. Nothing done.")
            response = "escalated"
        else:
            subject = agent.mailbox.get(notice.email_id).subject
            label = "Follow up? No reply yet to" if kind == "nudge" else "Deadline coming up for"
            answer = input(f"\n    {label} \"{subject}\". Timing [enter] fine · [e]arly · [l]ate: ").strip().lower()
            verdict = {"e": "too_early", "l": "too_late"}.get(answer, "ok")
            agent.timing_feedback(notice, verdict)
            response = f"{kind} timing {verdict.replace('_', ' ')}"
        self.audit.response(notice.email_id, response)


def try_agent(persona: str, count: int, offline: bool) -> None:
    agent, feed = setup(persona, count, offline)
    Session(agent, feed, AuditLog(f"runs/audit_{datetime.now():%Y%m%d_%H%M%S}.csv")).run()
