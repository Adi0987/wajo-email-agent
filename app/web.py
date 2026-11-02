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
from app.assistant import Assistant
from app.feed import build

PAGE = Path(__file__).with_name("index.html")


class App:
    def __init__(self, persona: str, count: int, offline: bool):
        agent, feed, narrator, self.source = build(persona, count, offline)
        self.audit_path = f"runs/audit_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self.assistant = Assistant(agent, narrator, AuditLog(self.audit_path))
        self.feed = deque(feed)
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

    def answer(self, form: dict) -> None:
        self.assistant.answer(int(form["id"]), form["reply"])

    def wait(self, form: dict) -> None:
        self.assistant.wait(float(form.get("days", 1)))

    def state(self) -> dict:
        mailbox = self.assistant.agent.mailbox
        inbox = []
        for email in mailbox.emails.values():
            if email.sender == mailbox.user_address or email.id not in self.assistant.shown:
                continue
            status = ("Trash" if email.id in mailbox.trashed else "Archived" if email.id in mailbox.archived
                      else "Draft ready" if email.id in mailbox.drafts else "Inbox")
            inbox.append({"subject": email.subject or "(no subject)", "sender": email.sender, "status": status,
                          "labels": sorted(mailbox.labels.get(email.id, ()))})
        return {"source": self.source, "user": mailbox.user_address, "remaining": len(self.feed),
                "clock": f"{self.assistant.clock:%a %b %d %Y}" if self.assistant.clock else "",
                "messages": self.assistant.messages, "inbox": inbox[::-1], "audit": self.audit_path}


def serve(persona: str, count: int, offline: bool, port: int = 8000) -> None:
    app = App(persona, count, offline)
    routes = {"/api/next": app.next, "/api/plant": app.plant, "/api/answer": app.answer, "/api/wait": app.wait}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/state":
                self.send(json.dumps(app.state()), "application/json")
            else:
                self.send(PAGE.read_text(), "text/html")

        def do_POST(self):
            form = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            try:
                routes[self.path](form)
            except Exception as error:     # show the problem on the page instead of dropping the request
                app.assistant.note(f"Something went wrong: {error}")
            self.send(json.dumps(app.state()), "application/json")

        def send(self, body: str, content_type: str) -> None:
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
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
