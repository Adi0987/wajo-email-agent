"""`python3 wajo.py ui`: the assistant as a web page on http://localhost:8000.

Standard library only. The page calls a small JSON API; every call returns the whole state.
"""
import json
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from agent.audit import AuditLog
from agent.models import Email
from app import session_log
from app.assistant import Assistant
from app.feed import available, build, defaults

PAGE = Path(__file__).with_name("index.html")


class App:
    def __init__(self, settings: dict):
        self.session(settings)

    def session(self, settings: dict) -> None:
        """Starts a fresh session: new agent (nothing learned), new emails, new audit log."""
        s = {**defaults(), **settings}
        s["count"] = int(s["count"])
        session = build(s["source"], s["persona"], s["count"], s["llm"])   # may fail: keep the old session
        self.settings, self.source = s, session.description
        self.assistant = Assistant(session.agent, session.llm, session.profile, AuditLog())
        self.log_folder = session_log.new_folder()
        self.feed = deque(session.feed)
        self.planted = 0

    def next(self, _: dict) -> None:
        if self.feed:
            self.assistant.deliver(self.feed.popleft())

    def plant(self, form: dict) -> None:
        """An email written in the admin panel. "From me" makes it the user's own sent mail."""
        mailbox, self.planted = self.assistant.agent.mailbox, self.planted + 1
        from_me = bool(form.get("from_me"))
        sender = mailbox.user_address if from_me else form["sender"].strip().lower()
        subject = form.get("subject", "").strip()
        thread = next((e.thread_id for e in mailbox.emails.values()
                       if subject.lower().startswith("re: ") and e.subject == subject[4:]), f"p{self.planted}")
        sent_at = (self.assistant.clock or datetime.now()) + timedelta(minutes=1)
        email = Email(id=f"p{self.planted}", thread_id=thread, sender=sender,
                      to=(form.get("to", "").strip().lower() or "someone@example.com",) if from_me else (mailbox.user_address,),
                      subject=subject, body=form.get("body", ""), sent_at=sent_at,
                      authenticated=bool(form.get("authenticated")), has_unsubscribe=bool(form.get("newsletter")))
        if from_me:                       # your own mail isn't processed, but can get a follow-up nudge
            self.assistant.clock = sent_at
            mailbox.receive(email)
        else:
            self.assistant.deliver(email)

    def say(self, form: dict) -> None:
        self.assistant.say(form.get("text", ""))

    def profile(self, form: dict) -> None:
        self.assistant.profile.replace(form["text"])

    def wait(self, form: dict) -> None:
        self.assistant.wait(float(form.get("days", 1)))

    def state(self) -> dict:
        mailbox, waiting = self.assistant.agent.mailbox, self.assistant.waiting()
        inbox = []
        for email in mailbox.emails.values():
            if email.sender == mailbox.user_address or email.id not in self.assistant.shown:
                continue
            section = ("Waiting on you" if email.id in waiting else "Trash" if email.id in mailbox.trashed
                       else "Archived" if email.id in mailbox.archived else "Drafts ready" if email.id in mailbox.drafts
                       else "Inbox")
            inbox.append({"subject": email.subject or "(no subject)", "sender": email.sender, "section": section,
                          "labels": sorted(mailbox.labels.get(email.id, ()))})
        return {"source": self.source, "settings": self.settings, "available": available(),
                "preferences": self.assistant.learned(), "timing": self.assistant.timing(),
                "scheduled": self.assistant.scheduled(),
                "profile": self.assistant.profile.notes,
                "user": mailbox.user_address, "remaining": len(self.feed),
                "clock": f"{self.assistant.clock:%a %b %d %Y}" if self.assistant.clock else "",
                "messages": self.assistant.messages, "inbox": inbox[::-1], "log": str(self.log_folder)}



def serve(settings: dict, port: int = 8000) -> None:
    app = App(settings)
    routes = {"/api/next": app.next, "/api/plant": app.plant, "/api/say": app.say, "/api/wait": app.wait,
              "/api/session": app.session, "/api/profile": app.profile}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/state":
                self.send(json.dumps(app.state()), "application/json")
            elif self.path == "/api/audit.csv":       # built from memory on request; never saved
                self.send(app.assistant.audit.csv_text(), "text/csv", attachment="wajo_audit.csv")
            else:
                self.send(PAGE.read_text(), "text/html")

        def do_POST(self):
            form = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            try:
                routes[self.path](form)
            except Exception as error:     # show the problem on the page instead of dropping the request
                app.assistant.note(f"Something went wrong: {error}")
            session_log.write(app.log_folder, app.assistant, app.source)
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

        def log_message(self, *args):    # keep the terminal quiet
            pass

    url = f"http://localhost:{port}"
    print(f"Wajo assistant running at {url}  ({app.source}). Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n" + app.assistant.audit.summary())
