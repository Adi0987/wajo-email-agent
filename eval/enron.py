"""Loads one person's mail from the Enron dataset.

Reads either the Kaggle zip (one emails.csv: path, raw message) or the CMU maildir folder.
Paths look like <person>/_sent_mail/1. and <person>/inbox/1.
"""
import csv
import io
import random
import sys
import zipfile
from email import message_from_bytes
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Iterator, Optional

from agent.models import Email

SENT_FOLDERS = ("_sent_mail", "sent_items", "sent")


def raw_messages(source: str, person: str) -> Iterator[tuple[str, bytes]]:
    """(folder, raw message) for each of the person's emails."""
    if source.endswith(".zip"):
        csv.field_size_limit(sys.maxsize)
        with zipfile.ZipFile(source) as archive:
            rows = csv.reader(io.TextIOWrapper(archive.open("emails.csv"), encoding="utf-8", newline=""))
            for path, message in rows:
                parts = path.split("/")
                if parts[0] == person and len(parts) == 3:
                    yield parts[1], message.encode("utf-8")
    else:
        for path in sorted((Path(source) / person).glob("*/*")):
            if path.is_file():
                yield path.parent.name, path.read_bytes()


def parse(raw: bytes, email_id: str) -> Optional[Email]:
    message = message_from_bytes(raw)
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


def load(source: str, person: str, count: int, seed: int = 0) -> tuple[str, list[Email], list[Email]]:
    """(user address, the person's sent mail, `count` random inbox emails in date order)."""
    sent_raw, inbox_raw = [], []
    for folder, raw in raw_messages(source, person):
        if folder in SENT_FOLDERS:
            sent_raw.append(raw)
        elif folder == "inbox":
            inbox_raw.append(raw)
    sent = [e for i, raw in enumerate(sent_raw) if (e := parse(raw, f"s{i}"))]
    if not sent:
        raise SystemExit(f"No sent mail found for {person} in {source}")
    user = max({e.sender for e in sent}, key=lambda a: sum(e.sender == a for e in sent))
    picked = random.Random(seed).sample(inbox_raw, min(count, len(inbox_raw)))
    inbox = [e for i, raw in enumerate(picked) if (e := parse(raw, f"m{i}"))]
    return user, sent, sorted(inbox, key=lambda e: e.sent_at)
