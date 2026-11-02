"""Check 2 flags: classifier labels OR fixed patterns.

The proposer's output is only used for the recipient check, never trusted
as a judgment.
"""

import re

from policy.mail_client import MailClient
from policy.models import Action, Email, Flags

MONEY_PATTERNS = [
    r"[$€£]\s?\d",  # amounts
    r"\binvoice\b",
    r"\biban\b",
    r"\bwire\b",
]


def money_pattern(email: Email) -> bool:
    text = f"{email.subject}\n{email.body}".lower()
    return any(re.search(pattern, text) for pattern in MONEY_PATTERNS)


def recipient_outside(action: Action, mailbox: MailClient) -> bool:
    """True if the action sends to anyone outside the thread and contacts."""
    thread = mailbox.thread(mailbox.get(action.email_id).thread_id)
    in_thread = {e.sender for e in thread} | {address for e in thread for address in e.to}
    allowed = in_thread | mailbox.contacts()
    return any(address not in allowed for address in action.to)


def detect_flags(email: Email, action: Action, labels: dict, mailbox: MailClient) -> Flags:
    """labels: classifier output, e.g. {"money": True, "injection": False}."""
    outside = recipient_outside(action, mailbox)
    return Flags(
        money=labels.get("money", False) or money_pattern(email),
        injection=labels.get("injection", False) or outside,
        outside=outside,
    )
