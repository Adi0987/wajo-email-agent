"""Simulated user with hidden, consistent preferences."""
import random
from datetime import datetime

from agent.agent import Agent
from agent.notices import Notice
from agent.senders import other_party
from eval.inbox import Case

WAIT_DAYS = {"same_domain": 2.0, "contact": 5.0}    # preferred wait before a follow-up
LEAD_DAYS = {"same_domain": 3.0, "contact": 3.0}    # preferred reminder lead before a deadline
TOLERANCE = 1.5                                     # within 1.5x either way counts as "ok"


def nudge_verdict(waited: float, preferred: float) -> str:
    if waited < preferred / TOLERANCE:
        return "too_early"
    if waited > preferred * TOLERANCE:
        return "too_late"
    return "ok"


def reminder_verdict(lead: float, preferred: float) -> str:
    if lead > preferred * TOLERANCE:
        return "too_early"
    if lead < preferred / TOLERANCE:
        return "too_late"
    return "ok"


class SimUser:
    def __init__(self, cases: list[Case], seed: int, noise: float = 0.05, notices_silent: float = 0.5):
        self.truth = {c.email.id: c for c in cases}
        self.rng = random.Random(seed)
        self.noise = noise                     # chance a response is flipped
        self.notices_silent = notices_silent   # chance a wrong silent action is noticed
        self.timing: list[tuple[str, str]] = []   # (notice kind, verdict)
        self.history: list[tuple[datetime, str, str]] = []   # (time, email id, what the user did)

    def wants(self, kind: str, email_id: str) -> bool:
        """True if the user wants this action, flipped with probability `noise`."""
        correct = self.truth[email_id].correct == kind
        return correct != (self.rng.random() < self.noise)

    def respond(self, agent: Agent, notice: Notice, now: datetime) -> None:
        if notice.email_id not in self.truth:
            return                           # mail the agent sent itself, not part of the inbox
        correct = self.truth[notice.email_id].correct
        chosen = correct if notice.action and correct != notice.action.kind else None
        if notice.kind == "ask":
            if self.wants(notice.action.kind, notice.email_id):
                agent.approve(notice, now)
                self._log(now, notice, "approves")
            else:
                agent.reject(notice, chosen=chosen)
                self._log(now, notice, f"rejects, wants {chosen}" if chosen else "rejects")
        elif notice.kind == "notify":
            if self.wants(notice.action.kind, notice.email_id):
                agent.confirm(notice)
                self._log(now, notice, "confirms")
            else:
                agent.undo(notice.action, chosen=chosen)
                self._log(now, notice, f"undoes, wants {chosen}" if chosen else "undoes")
        elif notice.kind in ("nudge", "reminder"):
            verdict = self._timing(agent, notice, now)
            self.timing.append((notice.kind, verdict))
            agent.timing_feedback(notice, verdict)
            self._log(now, notice, f"says timing is {verdict.replace('_', ' ')}")

    def review_silent(self, agent: Agent, entry: dict) -> None:
        action = entry["action"]
        if action.email_id not in self.truth:
            return
        wrong = self.truth[action.email_id].correct != action.kind
        if wrong and self.rng.random() < self.notices_silent:
            correct = self.truth[action.email_id].correct
            agent.undo(action, chosen=correct)
            self.history.append((entry["at"], action.email_id, f"notices and undoes, wants {correct}"))

    def _log(self, now: datetime, notice: Notice, text: str) -> None:
        self.history.append((now, notice.email_id, f"{text} ({notice.kind})"))

    def _timing(self, agent: Agent, notice: Notice, now: datetime) -> str:
        email = agent.mailbox.get(notice.email_id)
        _, category = other_party(email, agent.mailbox)
        if notice.kind == "nudge":
            waited = (now - email.sent_at).total_seconds() / 86400
            return nudge_verdict(waited, WAIT_DAYS.get(category, 3.0))
        lead = (self.truth[email.id].deadline - now).total_seconds() / 86400
        return reminder_verdict(lead, LEAD_DAYS.get(category, 3.0))
