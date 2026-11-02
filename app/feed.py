"""Builds a session for `ui` and `try`: the mail server, Wajo, and where new emails come from.

The user is user@example.com. New emails are written by the LLM when the user asks for one (needs LLM_API_KEY in .env);
without a key, they come from the synthetic test inbox and Wajo runs on simple rules.
"""

from dataclasses import dataclass

from agent.brain import LLMBrain, OfflineBrain
from agent.classifier import Classifier, offline_classify
from agent.llm import LLM, settings
from agent.wajo import Wajo
from app.audit import AuditLog
from eval.inbox import USER, build_inbox
from mailsim.generator import EmailGenerator
from mailsim.server import MailServer, connect
from policy.gate import Gate


def available() -> dict:
    return {"llm": bool(settings()["key"])}


def defaults() -> dict:
    return {"llm": "llm" if available()["llm"] else "offline"}


@dataclass
class Session:
    server: MailServer  # the simulated mail server (the inbox the user sees)
    wajo: Wajo  # reaches it only through MCP tool calls, via the gate
    emails: EmailGenerator  # the outside world: new mail when the user asks for it
    description: str


def build(llm_choice: str) -> Session:
    server, mailbox = connect(USER)
    gate = Gate(mailbox)
    if llm_choice == "llm":
        llm = LLM(cache_path=None)  # in memory only: nothing about this session touches the disk
        wajo = Wajo(gate, LLMBrain(llm), Classifier(llm), audit=AuditLog())
        return Session(server, wajo, EmailGenerator(llm, []), f"new emails and decisions by {llm.config['model']}")
    test_inbox = [c.email for c in build_inbox(seed=7) if c.incoming]
    wajo = Wajo(gate, OfflineBrain(), offline_classify, audit=AuditLog())
    return Session(
        server, wajo, EmailGenerator(None, test_inbox), "synthetic test inbox · offline stand-in (no API key)"
    )
