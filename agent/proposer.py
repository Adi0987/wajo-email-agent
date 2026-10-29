"""LLM step 1: suggest an action. It never decides the autonomy level."""
from agent.checks import ACTIONS
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Action, Email
from agent.prompts import PROPOSE, format_email


class Proposer:
    def __init__(self, llm: LLM):
        self.llm = llm

    def __call__(self, email: Email, mailbox: Mailbox) -> Action:
        reply = self.llm.complete_json(PROPOSE.format(user=mailbox.user_address), format_email(email))
        kind = reply.get("kind")
        if kind not in ACTIONS:
            return Action("keep", email.id)
        return Action(kind, email.id,
                      label=str(reply.get("label") or ""),
                      to=tuple(reply.get("to") or ()),
                      body=str(reply.get("body") or ""))
