"""Sender category, from the exact sender address and authentication result."""
from agent.mailbox import Mailbox
from agent.models import Email

CATEGORIES = ("contact", "same_domain", "newsletter", "unknown")


def domain_of(address: str) -> str:
    """Domain in ASCII form, so Unicode lookalikes don't match real domains."""
    domain = address.rsplit("@", 1)[-1]
    try:
        return domain.encode("idna").decode("ascii")
    except UnicodeError:
        return "invalid:" + domain


def sender_category(email: Email, mailbox: Mailbox) -> str:
    if email.authenticated and email.sender in mailbox.contacts():
        return "contact"
    if email.authenticated and domain_of(email.sender) == mailbox.user_domain:
        return "same_domain"
    if email.has_unsubscribe:
        return "newsletter"
    return "unknown"
