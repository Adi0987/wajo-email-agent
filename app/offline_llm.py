"""A simple rule-based stand-in for the LLM, so `try` and `ui` work without an API key.

Works on any email, including ones planted from the admin panel. Not used by the eval.
"""
import re
from datetime import datetime, timedelta
from typing import Optional

from agent.mailbox import Mailbox
from agent.models import Action, Email

ADDRESS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DUE = re.compile(r"\b(?:by|due|before)\s+(?:\w+,\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|[a-z]{3,9}\s+\d{1,2})", re.I)


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
    return {"money": False, "deadline": deadline(email),
            "injection": "ignore your previous instructions" in text or "assistant:" in text}


def deadline(email: Email) -> Optional[datetime]:
    """'by Friday' or 'due Nov 06' in the subject or body, as a date after the email was sent."""
    match = DUE.search(f"{email.subject} {email.body}")
    if not match:
        return None
    when = match.group(1).lower()
    sent = email.sent_at.replace(hour=9, minute=0, second=0, microsecond=0)
    if when in WEEKDAYS:
        return sent + timedelta(days=(WEEKDAYS.index(when) - sent.weekday() - 1) % 7 + 1)
    try:
        day = datetime.strptime(f"{when} {sent.year}", "%b %d %Y")
    except ValueError:
        try:
            day = datetime.strptime(f"{when} {sent.year}", "%B %d %Y")
        except ValueError:
            return None
    return day.replace(hour=9)
