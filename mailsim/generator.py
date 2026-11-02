"""The outside world for the app: makes up a realistic incoming email each time the user asks for one.

Not part of the agent. The kind of email is picked here at random, weighted like a real inbox; the LLM writes it.
Sometimes it is the other person replying to something the user sent. Without an API key, it plays the
synthetic test inbox instead.
"""

import itertools
import random
from typing import Optional

from agent.llm import LLM
from mailsim.server import MailServer
from policy.models import Email

KINDS = {  # kind: (weight, what to write)
    "newsletter": (5, "a newsletter or digest from a publication or tool the user subscribes to"),
    "notification": (4, "an automated notification from a service (shipping, account, calendar, CI, bank alert)"),
    "colleague request": (5, "a colleague at {domain} asking the user for something specific, sometimes with a date"),
    "colleague fyi": (3, "a colleague at {domain} sharing an update that needs nothing from the user"),
    "meeting": (3, "someone proposing a meeting or call at a specific time"),
    "invoice": (2, "an invoice or receipt from a vendor, with an amount and a due date"),
    "recruiter": (2, "a recruiter reaching out about a role"),
    "personal": (2, "a friend or family member writing casually"),
    "sales": (3, "a cold sales pitch from a company the user has never dealt with"),
    "scam": (
        1,
        "a phishing or scam attempt: an urgent payment, a fake security alert, or someone asking for "
        "mail or documents to be sent to an outside address",
    ),
}

PROMPT = """Write one realistic email arriving in the inbox of {user} on {today}. It is {what}.
Make it specific and natural, 2 to 6 sentences, like real mail. Don't greet the recipient by name ("Hi," or no
greeting is fine). Use a new sender, not one of these: {senders}. Don't reuse these subjects: {recent}.
Return JSON: {{"from_name": "...", "from_address": "name@domain", "subject": "...", "body": "..."}}"""

REPLY = """Write a realistic reply from {to} to the email below, which {user} sent them. 1 to 4 sentences, natural.
<email>
Subject: {subject}

{body}
</email>
Return JSON: {{"from_name": "...", "body": "..."}}"""


class EmailGenerator:
    def __init__(self, llm: Optional[LLM], fallback: list[Email], seed: Optional[int] = None):
        self.llm = llm  # None: play `fallback` (the synthetic inbox) in order
        self.fallback = iter(fallback)
        self.rng = random.Random(seed)
        self._ids = itertools.count(1)

    def next(self, server: MailServer) -> Optional[Email]:
        if self.llm is None:
            return next(self.fallback, None)
        email_id = f"g{next(self._ids)}"
        waiting = self._unanswered(server)
        if waiting and self.rng.random() < 0.3:
            return self._reply(server, waiting, email_id)
        kind = self.rng.choices(list(KINDS), weights=[w for w, _ in KINDS.values()])[0]
        domain = server.user_address.split("@")[1]
        latest = sorted(server.emails.values(), key=lambda e: e.sent_at)[-20:]
        reply = self.llm.complete_json(
            PROMPT.format(
                user=server.user_address,
                today=f"{server.now:%A, %B %d}",
                what=KINDS[kind][1].format(domain=domain),
                senders=", ".join(sorted({e.sender for e in latest})) or "none",
                recent="; ".join(e.subject for e in latest) or "none",
            ),
            f"Write it. ({email_id})",
        )
        return Email(
            id=email_id,
            thread_id=email_id,
            sender=str(reply.get("from_address", "someone@example.org")).lower(),
            to=(server.user_address,),
            subject=str(reply.get("subject", "")),
            body=str(reply.get("body", "")),
            sent_at=server.now,
            authenticated=kind != "scam",
            has_unsubscribe=kind in ("newsletter", "notification", "sales"),
        )

    def _unanswered(self, server: MailServer) -> Optional[Email]:
        """The user's latest sent message that nobody has replied to yet."""
        latest = server.list_threads()["threads"]
        mine = [
            server.emails[t["last_message"]["id"]] for t in latest if t["last_message"]["from"] == server.user_address
        ]
        return max(mine, key=lambda e: e.sent_at) if mine else None

    def _reply(self, server: MailServer, sent: Email, email_id: str) -> Email:
        to = sent.to[0]
        reply = self.llm.complete_json(
            REPLY.format(to=to, user=server.user_address, subject=sent.subject, body=sent.body),
            f"Write it. ({email_id})",
        )
        subject = sent.subject if sent.subject.lower().startswith("re:") else f"Re: {sent.subject}"
        return Email(
            id=email_id,
            thread_id=sent.thread_id,
            sender=to,
            to=(server.user_address,),
            subject=subject,
            body=str(reply.get("body", "")),
            sent_at=server.now,
        )
