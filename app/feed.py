"""Builds the agent and the emails to feed it, for `ui` and `try`.

Emails come from a random sample of a real Enron inbox (needs enron-email-dataset.zip here)
or from the synthetic inbox. Decisions come from DeepSeek (needs LLM_API_KEY) or from a
rule-based stand-in that needs no key.
"""
import os
from pathlib import Path

from agent.agent import Agent
from agent.classifier import Classifier
from agent.llm import LLM, load_env
from agent.mailbox import Mailbox
from agent.models import Email
from agent.proposer import Proposer
from app import enron, offline_llm
from app.narrator import Narrator
from eval.inbox import USER, build_inbox

ENRON_ZIP = "enron-email-dataset.zip"


def available() -> dict:
    load_env()
    return {"enron": Path(ENRON_ZIP).exists(), "deepseek": bool(os.environ.get("LLM_API_KEY"))}


def defaults() -> dict:
    """The best session this machine can run."""
    have = available()
    return {"source": "enron" if have["enron"] else "synthetic", "persona": "kaminski-v", "count": 20,
            "llm": "deepseek" if have["deepseek"] else "offline"}


def build(source: str, persona: str, count: int, llm_choice: str) -> tuple[Agent, list[Email], Narrator, str]:
    """(agent, emails to deliver in order, narrator, one line describing the session)."""
    if source == "enron":
        user, feed = enron.sample_inbox(ENRON_ZIP, persona, count)
        mailbox = Mailbox(user)
        where = f"{len(feed)} random emails from {persona}'s Enron inbox"
    else:
        cases = build_inbox(seed=7)
        mailbox = Mailbox(USER)
        for case in cases:
            if not case.incoming:
                mailbox.receive(case.email)    # the user's past mail, so contacts exist
        feed = [c.email for c in cases if c.incoming][:count]
        where = f"{len(feed)} emails from the synthetic inbox"
    if llm_choice == "deepseek":
        llm = LLM(cache_path=".llm_cache_local.json")   # keeps these emails out of the eval cache
        return Agent(mailbox, Proposer(llm), Classifier(llm)), feed, Narrator(llm), f"{where} · DeepSeek"
    agent = Agent(mailbox, offline_llm.propose, offline_llm.classify)
    return agent, feed, Narrator(None), f"{where} · offline stand-in (no API key)"
