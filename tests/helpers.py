from datetime import datetime

from mailsim.server import MailServer, connect
from policy.mail_client import MailClient
from policy.models import Email

USER = "user@example.com"
T0 = datetime(2026, 11, 1, 9, 0)


def make_email(
    id="e1", sender="friend@gmail.com", body="hi?", subject="hello", thread_id=None, to=(USER,), sent_at=T0, **kwargs
) -> Email:
    return Email(
        id=id, thread_id=thread_id or id, sender=sender, to=to, subject=subject, body=body, sent_at=sent_at, **kwargs
    )


def make_mailbox(*emails: Email) -> MailClient:
    """The agent's mail client, connected to a fresh simulated server holding `emails`."""
    server, client = connect(USER)
    for email in emails:
        server.deliver(email)
    return client


def server_of(client: MailClient) -> MailServer:
    """The simulated server behind a client, so tests can check what happened to the mail."""
    return client.transport.__self__
