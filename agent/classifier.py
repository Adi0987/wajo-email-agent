"""Labels each new email: money, injection, deadline, kind. Isolated from the rest of the agent:
it sees only the email, never the conversation, the proposed action or what the user wants.

Classifier uses the LLM; offline_classify is a rule-based stand-in for running without an API key.
"""

import re
from datetime import datetime, timedelta
from typing import Optional

from agent.llm import LLM
from agent.prompts import CLASSIFY, format_email
from policy.models import Email

KINDS = (
    "newsletter",
    "spam",
    "notification",
    "fyi",
    "request",
    "meeting",
    "personal",
    "finance",
    "recruiting",
    "other",
)


class Classifier:
    def __init__(self, llm: LLM):
        self.llm = llm

    def __call__(self, email: Email) -> dict:
        reply = self.llm.complete_json(CLASSIFY, format_email(email))
        return {
            "money": reply.get("money") is True,
            "injection": reply.get("injection") is True,
            "deadline": parse_date(reply.get("deadline")),
            "kind": reply.get("kind") if reply.get("kind") in KINDS else "other",
        }


def parse_date(value) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").replace(hour=9)
    except ValueError:
        return None


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DUE = re.compile(
    r"\b(?:by|due|before)\s+(?:\w+,\s+)?"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|[a-z]{3,9}\s+\d{1,2})",
    re.I,
)


def offline_classify(email: Email) -> dict:
    text = email.body.lower()
    return {
        "money": False,
        "deadline": deadline(email),
        "kind": kind(email),
        "injection": "ignore your previous instructions" in text or "assistant:" in text,
    }


def kind(email: Email) -> str:
    text = f"{email.subject} {email.body}".lower()
    if email.has_unsubscribe:
        return "newsletter"
    if any(word in text for word in ("invoice", "payment", "$")):
        return "finance"
    if any(word in text for word in ("meet", "call", "calendar", "sync")):
        return "meeting"
    if "?" in text or "please" in text:
        return "request"
    return "fyi"


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
