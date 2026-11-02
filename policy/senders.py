"""Sender category, from the exact sender address and authentication result."""

from policy.mail_client import MailClient
from policy.models import Email


def domain_of(address: str) -> str:
    """Domain in ASCII form, so Unicode lookalikes don't match real domains."""
    domain = address.rsplit("@", 1)[-1]
    try:
        return domain.encode("idna").decode("ascii")
    except UnicodeError:
        return "invalid:" + domain


def category_of(address: str, authenticated: bool, has_unsubscribe: bool, mailbox: MailClient) -> str:
    """same_domain, contact, newsletter or unknown."""
    if authenticated and domain_of(address) == mailbox.user_domain:
        return "same_domain"
    if authenticated and address in mailbox.contacts():
        return "contact"
    if has_unsubscribe:
        return "newsletter"
    return "unknown"


def sender_category(email: Email, mailbox: MailClient) -> str:
    return category_of(email.sender, email.authenticated, email.has_unsubscribe, mailbox)


def other_party(email: Email, mailbox: MailClient) -> tuple[str, str]:
    """(address, category) of the person on the other side of the email.

    For the user's own sent mail, that is the first recipient.
    """
    if email.sender == mailbox.user_address:
        address = email.to[0]
        return address, category_of(address, True, False, mailbox)
    return email.sender, sender_category(email, mailbox)
