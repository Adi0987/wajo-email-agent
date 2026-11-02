"""`python3 wajo.py ui`: the assistant as a web page on http://localhost:8000.

Standard library only. The page calls a small JSON API; every call returns the whole state.
"""

import json
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from agent.context import scheduled
from app import diagnostics, session_log
from app.feed import available, build, defaults
from policy.models import Email

PAGE = Path(__file__).with_name("index.html")


class App:
    def __init__(self, settings: dict):
        self.session(settings)

    def session(self, settings: dict) -> None:
        """Starts a fresh session: new agent (nothing learned), new emails, new audit log."""
        s = {**defaults(), **{k: v for k, v in settings.items() if k == "llm"}}
        session = build(s["llm"])  # may fail: keep the old session
        self.settings, self.source = s, session.description
        self.server = session.server
        self.wajo = session.wajo
        self.log_folder = session_log.new_folder()
        self.emails = session.emails
        self.planted = 0
        self.clock = datetime.now().replace(second=0, microsecond=0)  # the session's clock; Wait moves it
        self.server.now = self.clock
        self.unread: list[Email] = []  # arrived, but Wajo hasn't looked yet

    def advance(self, to: datetime) -> datetime:
        self.clock = max(self.clock or to, to)
        self.server.now = self.clock
        return self.clock

    def arrive(self, email: Email) -> None:
        """The outside world delivers an email; it arrives now and shows up right away."""
        self.advance(self.clock + timedelta(minutes=1))
        email = self.server.receive(email)
        self.wajo.email_arrived(email)
        self.unread.append(email)

    def next(self, _: dict) -> None:
        """The next sampled email lands in the inbox. The page then calls process()."""
        email = self.emails.next(self.server)
        if email:
            self.arrive(email)
        else:
            self.wajo.note("The test inbox has no more emails. Start a new session in Admin.")

    def process(self, _: dict) -> None:
        """Wajo looks at what arrived, then anything that's due."""
        while self.unread:
            self.wajo.on_email(self.unread.pop(0), self.clock)
        self.wajo.on_tick(self.clock)

    def plant(self, form: dict) -> None:
        """An email written in the admin panel. "From me" makes it the user's own sent mail."""
        mailbox, self.planted = self.server, self.planted + 1
        from_me = bool(form.get("from_me"))
        sender = mailbox.user_address if from_me else form["sender"].strip().lower()
        subject = form.get("subject", "").strip()
        thread = next(
            (
                e.thread_id
                for e in mailbox.emails.values()
                if subject.lower().startswith("re: ") and e.subject == subject[4:]
            ),
            f"p{self.planted}",
        )
        sent_at = self.clock + timedelta(minutes=1)
        email = Email(
            id=f"p{self.planted}",
            thread_id=thread,
            sender=sender,
            to=(form.get("to", "").strip().lower() or "someone@example.com",) if from_me else (mailbox.user_address,),
            subject=subject,
            body=form.get("body", ""),
            sent_at=sent_at,
            authenticated=bool(form.get("authenticated")),
            has_unsubscribe=bool(form.get("newsletter")),
        )
        if from_me:  # your own mail isn't processed, but can get a follow-up nudge
            self.advance(sent_at)
            mailbox.deliver(email)
        else:
            self.arrive(email)

    def say(self, form: dict) -> None:
        self.advance(self.clock or datetime.now())
        self.wajo.on_user(form.get("text", ""), self.clock)

    def profile(self, form: dict) -> None:
        self.wajo.profile.replace(form["text"])

    def wait(self, form: dict) -> None:
        """Time passes a day at a step, so each follow-up and reminder comes up on its own day.
        Days when nothing happens aren't announced."""
        days = float(form.get("days", 1))
        while days > 0:
            step = min(days, 1.0)
            self.advance(self.clock + timedelta(days=step))
            days -= step
            before = len(self.wajo.messages)
            self.wajo.on_tick(self.clock)
            if len(self.wajo.messages) > before or days <= 0:
                self.wajo.note(f"It's now {self.clock:%a %b %d %Y}.")
                self.wajo.messages.insert(before, self.wajo.messages.pop())

    def state(self) -> dict:
        mailbox, waiting = self.server, self.wajo.waiting()
        inbox = []
        for email in mailbox.emails.values():
            if email.sender == mailbox.user_address:
                inbox.append(
                    {
                        "subject": email.subject or "(no subject)",
                        "sender": "to " + ", ".join(email.to),
                        "section": "Sent",
                        "labels": [],
                        "date": f"{email.sent_at:%b %d}",
                        "sort": email.sent_at,
                    }
                )
                continue
            if email.id not in self.wajo.shown:
                continue
            section = (
                "Waiting on you"
                if email.id in waiting
                else (
                    "Trash"
                    if email.id in mailbox.trashed
                    else (
                        "Archived"
                        if email.id in mailbox.archived
                        else "Drafts ready" if email.id in mailbox.drafts else "Inbox"
                    )
                )
            )
            inbox.append(
                {
                    "subject": email.subject or "(no subject)",
                    "sender": email.sender,
                    "section": section,
                    "labels": sorted(mailbox.labels.get(email.id, ())),
                    "date": f"{email.sent_at:%b %d}",
                    "sort": email.sent_at,
                }
            )
        inbox.sort(key=lambda e: e.pop("sort"))
        return {
            "source": self.source,
            "settings": self.settings,
            "available": available(),
            "preferences": diagnostics.learned(self.wajo.gate),
            "timing": diagnostics.timing(self.wajo.gate),
            "scheduled": scheduled(self.wajo.gate),
            "profile": self.wajo.profile.notes,
            "user": mailbox.user_address,
            "clock": f"{self.clock:%a %b %d %Y}" if self.clock else "",
            "messages": self.wajo.messages,
            "inbox": inbox[::-1],
            "log": str(self.log_folder),
        }


def serve(settings: dict, port: int = 8000) -> None:
    app = App(settings)
    routes = {
        "/api/next": app.next,
        "/api/process": app.process,
        "/api/plant": app.plant,
        "/api/say": app.say,
        "/api/wait": app.wait,
        "/api/session": app.session,
        "/api/profile": app.profile,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/state":
                self.send(json.dumps(app.state()), "application/json")
            elif self.path == "/api/audit.csv":  # built from memory on request; never saved
                self.send(app.wajo.audit.csv_text(), "text/csv", attachment="wajo_audit.csv")
            else:
                self.send(PAGE.read_text(), "text/html")

        def do_POST(self):
            form = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            try:
                routes[self.path](form)
            except Exception as error:  # show the problem on the page instead of dropping the request
                app.wajo.note(f"Something went wrong: {error}")
            session_log.write(app.log_folder, app.wajo, app.source)
            self.send(json.dumps(app.state()), "application/json")

        def send(self, body: str, content_type: str, attachment: str = "") -> None:
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # keep the terminal quiet
            pass

    url = f"http://localhost:{port}"
    print(f"Wajo assistant running at {url}  ({app.source}). Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n" + app.wajo.audit.summary())
