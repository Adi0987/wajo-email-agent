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
from agent.models import Email, Level
from agent.notices import Notice
from agent.proposer import Proposer
from agent.rates import NOTIFY_AT, SILENT_AT
from agent.senders import other_party
from eval import enron
from eval.inbox import USER, build_inbox
from eval.llm_steps import llm_steps
from eval.style import BLUE, BOLD, CYAN, DIM, GREEN, RED, YELLOW, badge, level_word, paint

ENRON_ZIP = "enron-email-dataset.zip"
ACTION_REASON = {Level.SILENT: "safe to do alone", Level.ASK: "leaves the mailbox or can't be undone"}
EMAIL_REASON = {Level.SILENT: "nothing risky", Level.NOTIFY: "involves money",
                Level.ASK: "involves money", Level.ESCALATE: "looks like prompt injection"}


def setup(persona: str, count: int, offline: bool) -> tuple[Agent, list[Email]]:
    """The agent and the emails to feed it."""
    if not offline and Path(ENRON_ZIP).exists():
        print(f"Picking {count} random emails from {persona}'s inbox in {ENRON_ZIP}...")
        user, feed = enron.sample_inbox(ENRON_ZIP, persona, count)
        llm = LLM(cache_path=".llm_cache_local.json")   # keeps these emails out of the eval cache
        propose, classify = Proposer(llm), Classifier(llm)
        history = []
    else:
        cases = build_inbox(seed=7)
        user, history = USER, [c.email for c in cases if not c.incoming]
        feed = [c.email for c in cases if c.incoming][:count]
        propose, classify = llm_steps("stub", cases, seed=7)
    print(f"You are {user}. {len(feed)} emails will arrive one at a time.")
    mailbox = Mailbox(user)
    for email in history:       # synthetic inbox only: the user's past mail, so contacts exist
        mailbox.receive(email)
    return Agent(mailbox, propose, classify), feed


class Session:
    def __init__(self, agent: Agent, feed: list[Email], audit: AuditLog):
        self.agent, self.feed, self.audit = agent, feed, audit
        self.notices_seen = self.log_seen = 0

    def run(self) -> None:
        for number, email in enumerate(self.feed, 1):
            self.show_email(number, email)
            self.agent.mailbox.receive(email)
            self.agent.on_new_mail(email)
            self.agent.tick(email.sent_at)
            self.show_decisions()
            if input(paint("\n  [enter] next email · q quit ", DIM)).strip().lower() == "q":
                break
        print("\n" + paint("Session summary", BOLD) + "\n" + self.audit.summary())

    def show_email(self, number: int, email: Email) -> None:
        _, category = other_party(email, self.agent.mailbox)
        preview = " ".join(email.body.split())[:240]
        print("\n" + paint(f"━━━ Email {number}/{len(self.feed)} " + "━" * 50, BLUE))
        print(f"  {paint('From', DIM)}     {paint(email.sender, BOLD)} {paint(f'({category})', DIM)}"
              f"   {paint(f'{email.sent_at:%b %d %Y %H:%M}', DIM)}")
        print(f"  {paint('Subject', DIM)}  {paint(email.subject or '(no subject)', BOLD)}")
        print(f"           {paint(preview, DIM)}")

    def show_decisions(self) -> None:
        """Explains each new decision, then asks the user anything the agent needs."""
        while self.log_seen < len(self.agent.executor.log) or self.notices_seen < len(self.agent.notices):
            for entry in self.agent.executor.log[self.log_seen:]:
                self.log_seen += 1
                if not entry["approved"]:
                    self.explain(entry)
                elif entry["executed"]:
                    print(paint(f"  ✔ Done: {entry['action'].kind}", GREEN))
                else:
                    print(paint("  ✖ Not run: the action changed or is no longer allowed", RED))
            for notice in self.agent.notices[self.notices_seen:]:
                self.notices_seen += 1
                self.answer(notice)

    def explain(self, entry: dict) -> None:
        action, checks, level = entry["action"], entry["checks"], entry["level"]
        email = self.agent.mailbox.get(action.email_id)
        sender, category = other_party(email, self.agent.mailbox)
        rate = self.agent.rates.rate(action.kind, sender, category)
        target = f" → {', '.join(action.to)}" if action.to else ""
        print(f"\n  {paint('Agent wants to', DIM)}  {paint(action.kind + target, BOLD)}")
        print(f"  {paint('Decision', DIM)}        {badge(level)}  {paint('(the most cautious check wins)', DIM)}")
        rows = [("action", ACTION_REASON[checks["action"]], checks["action"]),
                ("email", EMAIL_REASON[checks["email"]], checks["email"]),
                ("learned", f"approval rate {rate:.0%} (Notify ≥{NOTIFY_AT:.0%}, Silent ≥{SILENT_AT:.0%})",
                 checks["learned"])]
        for name, reason, allowed in rows:
            print(f"    {paint(name.ljust(8), DIM)}{reason.ljust(52)} {level_word(allowed)}")
        if level == Level.SILENT:
            print(paint(f"  ✔ Done silently: {action.kind}", GREEN))
        self.audit.decision(entry, email, category, self.agent.labels.get(email.id, {}))

    def answer(self, notice: Notice) -> None:
        agent, kind = self.agent, notice.kind
        if kind == "ask":
            answer = input(paint(f"  ? Allow {notice.action.kind}? ", BOLD, YELLOW)
                           + paint("[y] yes · [n] no · or type the action you want "
                                   "(keep, archive, label, trash, draft_reply) ", DIM)).strip().lower()
            if answer in ("", "y", "yes"):
                agent.approve(notice, notice.at)
                response = "approved"
            else:
                chosen = None if answer in ("n", "no") else answer
                agent.reject(notice, chosen=chosen)
                response = f"rejected, wanted {chosen}" if chosen else "rejected"
                print(paint(f"  ✖ Rejected{f', noted you wanted {chosen}' if chosen else ''}", RED))
        elif kind == "notify":
            question = paint(f"  ✔ Did {notice.action.kind}. ", CYAN) + paint("[enter] fine · [u] undo ", DIM)
            if input(question).strip().lower() == "u":
                agent.undo(notice.action)
                response = "undone"
                print(paint("  ↶ Undone", YELLOW))
            else:
                agent.confirm(notice)
                response = "confirmed"
        elif kind == "escalate":
            print(paint("  ⚠ Escalated: suspected injection or phishing. Nothing done.", BOLD, RED))
            response = "escalated"
        else:
            subject = agent.mailbox.get(notice.email_id).subject
            label = "No reply yet to" if kind == "nudge" else "Deadline coming up for"
            question = (paint(f"\n  ⏰ {label} \"{subject}\". ", BOLD, BLUE)
                        + paint("Timing? [enter] fine · [e] too early · [l] too late ", DIM))
            verdict = {"e": "too_early", "l": "too_late"}.get(input(question).strip().lower(), "ok")
            agent.timing_feedback(notice, verdict)
            response = f"{kind} timing {verdict.replace('_', ' ')}"
        self.audit.response(notice.email_id, response)


def try_agent(persona: str, count: int, offline: bool) -> None:
    agent, feed = setup(persona, count, offline)
    Session(agent, feed, AuditLog(f"runs/audit_{datetime.now():%Y%m%d_%H%M%S}.csv")).run()
