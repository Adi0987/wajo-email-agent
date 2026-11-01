"""Loads one person's mail from the Enron dataset (maildir layout from cs.cmu.edu/~enron).

maildir/<person>/_sent_mail/* and maildir/<person>/inbox/* are RFC 822 files.
"""
import random
from email import message_from_bytes
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Optional

from agent.models import Email

SENT_FOLDERS = ("_sent_mail", "sent_items", "sent")


def parse(path: Path, email_id: str) -> Optional[Email]:
    message = message_from_bytes(path.read_bytes())
    try:
        sent_at = parsedate_to_datetime(message["Date"]).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None
    senders = getaddresses([message.get("From", "")])
    recipients = tuple(address.lower() for _, address in getaddresses(message.get_all("To", [])) if address)
    if not senders or not recipients:
        return None
    body = message.get_payload(decode=True) or b""
    return Email(id=email_id, thread_id=email_id, sender=senders[0][1].lower(), to=recipients,
                 subject=str(message.get("Subject", "")), body=body.decode("latin-1").strip(),
                 sent_at=sent_at, has_unsubscribe="List-Unsubscribe" in message)


def load(root: str, person: str, count: int, seed: int = 0) -> tuple[str, list[Email], list[Email]]:
    """(user address, the person's sent mail, `count` random inbox emails in date order)."""
    folder = Path(root) / person
    sent = [parse(p, f"s{i}") for i, p in enumerate(sorted(f for name in SENT_FOLDERS
                                                          for f in (folder / name).glob("*") if f.is_file()))]
    sent = [e for e in sent if e]
    if not sent:
        raise SystemExit(f"No sent mail found for {person} in {folder}")
    user = max({e.sender for e in sent}, key=lambda a: sum(e.sender == a for e in sent))
    inbox_files = sorted(f for f in (folder / "inbox").glob("*") if f.is_file())
    picked = random.Random(seed).sample(inbox_files, min(count, len(inbox_files)))
    inbox = [e for i, p in enumerate(picked) if (e := parse(p, f"m{i}"))]
    return user, sent, sorted(inbox, key=lambda e: e.sent_at)
