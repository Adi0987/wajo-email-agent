"""Builds the agent and the emails to feed it, for `try` and `ui`.

With enron-email-dataset.zip here: random emails from a real Enron inbox, with DeepSeek (needs LLM_API_KEY).
Otherwise: the synthetic inbox and a rule-based stand-in for the LLM (no key needed).
"""
from pathlib import Path

from agent.agent import Agent
from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Email
from agent.proposer import Proposer
from app import enron, offline_llm
from app.narrator import Narrator
from eval.inbox import USER, build_inbox

ENRON_ZIP = "enron-email-dataset.zip"


def build(persona: str, count: int, offline: bool) -> tuple[Agent, list[Email], Narrator, str]:
    """(agent, emails to deliver in order, narrator, one line saying where emails come from)."""
    if not offline and Path(ENRON_ZIP).exists():
        user, feed = enron.sample_inbox(ENRON_ZIP, persona, count)
        llm = LLM(cache_path=".llm_cache_local.json")   # keeps these emails out of the eval cache
        agent = Agent(Mailbox(user), Proposer(llm), Classifier(llm))
        return agent, feed, Narrator(llm), f"{len(feed)} random emails from {persona}'s Enron inbox (DeepSeek)"
    cases = build_inbox(seed=7)
    mailbox = Mailbox(USER)
    for case in cases:
        if not case.incoming:
            mailbox.receive(case.email)    # the user's past mail, so contacts exist
    feed = [c.email for c in cases if c.incoming][:count]
    agent = Agent(mailbox, offline_llm.propose, offline_llm.classify)
    return agent, feed, Narrator(None), f"{len(feed)} emails from the synthetic inbox (offline, no API key)"
