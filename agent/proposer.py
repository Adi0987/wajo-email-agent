"""LLM step 1: suggest an action. It never decides the autonomy level."""
from typing import Optional

from agent.checks import ACTIONS
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Action, Email
from agent.profile import Profile
from agent.prompts import PROFILE, PROPOSE, USUAL_CHOICE, format_email


class Proposer:
    def __init__(self, llm: LLM, profile: Optional[Profile] = None):
        self.llm = llm
        self.profile = profile    # read in full before every proposal

    def __call__(self, email: Email, mailbox: Mailbox, usual: Optional[str] = None) -> Action:
        system = PROPOSE.format(user=mailbox.user_address)
        if self.profile and self.profile.notes:
            system += PROFILE.format(notes=self.profile.text())
        if usual:
            system += USUAL_CHOICE.format(kind=usual)
        reply = self.llm.complete_json(system, format_email(email))
        kind = reply.get("kind")
        if kind not in ACTIONS:
            return Action("keep", email.id)
        return Action(kind, email.id,
                      label=str(reply.get("label") or ""),
                      to=tuple(reply.get("to") or ()),
                      body=str(reply.get("body") or ""))
