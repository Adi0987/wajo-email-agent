"""Picks random emails from one person's Enron inbox, as if they were arriving now.

Reads either the Kaggle zip (one emails.csv: path, raw message) or the CMU maildir folder.
Paths look like <person>/inbox/1.
"""
from collections import Counter
import csv
import io
import random
import sys
import zipfile
from email import message_from_bytes
from email.parser import BytesHeaderParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Iterator, Optional

from agent.models import Email

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
                 subject=" ".join(str(message.get("Subject", "")).split()), body=body.decode("latin-1").strip(),
                 sent_at=sent_at, has_unsubscribe="List-Unsubscribe" in message)


def sample_inbox(source: str, person: str, count: int) -> tuple[str, list[Email]]:
    """(the person's address, `count` random inbox emails in date order).

    Streams the dataset once and keeps only the sample (reservoir sampling).
    """
    rng = random.Random()
    picked: list[bytes] = []
    recipients = Counter()    # the person's own address is the most common recipient
    seen = 0
    for folder, raw in raw_messages(source, person):
        if folder != "inbox":
            continue
        seen += 1
        headers = BytesHeaderParser().parsebytes(raw)
        recipients.update(address.lower() for _, address in getaddresses(headers.get_all("To", [])) if address)
        if len(picked) < count:
            picked.append(raw)
        elif rng.random() < count / seen:
            picked[rng.randrange(count)] = raw
    inbox = sorted((e for i, raw in enumerate(picked) if (e := parse(raw, f"m{i}"))), key=lambda e: e.sent_at)
    if not inbox:
        raise ValueError(f"No inbox emails found for \"{person}\" in {source}")
    return recipients.most_common(1)[0][0], inbox
