from datetime import datetime

from agent.mailbox import Mailbox
from agent.models import Email

USER = "me@wajo.ai"
T0 = datetime(2026, 11, 1, 9, 0)


def make_email(id="e1", sender="friend@gmail.com", body="hi", subject="hello",
               thread_id=None, to=(USER,), sent_at=T0, **kwargs) -> Email:
    return Email(id=id, thread_id=thread_id or id, sender=sender, to=to,
                 subject=subject, body=body, sent_at=sent_at, **kwargs)


def make_mailbox(*emails: Email) -> Mailbox:
    mailbox = Mailbox(USER)
    for email in emails:
        mailbox.receive(email)
    return mailbox
