"""A simple rule-based stand-in for the LLM, so `try` and `ui` work without an API key.

Works on any email, including ones planted from the admin panel. Not used by the eval.
"""
import re

from agent.mailbox import Mailbox
from agent.models import Action, Email

ADDRESS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def propose(email: Email, mailbox: Mailbox, usual=None) -> Action:
    body = email.body.lower()
    addresses = [a for a in ADDRESS.findall(email.body) if a.lower() != email.sender]
    if addresses and "forward" in body:
        return Action("forward", email.id, to=(addresses[0].lower(),))   # naive: follows the request
    if usual:
        return Action(usual, email.id)
    if email.has_unsubscribe:
        return Action("archive", email.id)
    if "?" in email.body:
        return Action("draft_reply", email.id, body="Thanks for your note, I'll get back to you shortly.")
    return Action("keep", email.id)


def classify(email: Email) -> dict:
    text = email.body.lower()
    return {"money": False, "deadline": None,
            "injection": "ignore your previous instructions" in text or "assistant:" in text}
