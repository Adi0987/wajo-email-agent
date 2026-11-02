"""`python3 wajo.py try`: the assistant in your terminal. Emails arrive one at a time; reply in your own words."""

import textwrap

from app import session_log
from app.feed import build, defaults
from app.style import BLUE, BOLD, CYAN, DIM, GREEN, RED, YELLOW, paint

COLOR = {
    "user": BOLD,
    "ask": YELLOW,
    "notify": CYAN,
    "silent": GREEN,
    "escalate": RED,
    "nudge": BLUE,
    "reminder": BLUE,
    "remind_me": BLUE,
}
LABEL = {
    "ask": "asking",
    "notify": "did it, told you",
    "silent": "did it quietly",
    "escalate": "escalated",
    "nudge": "follow-up",
    "reminder": "reminder",
    "remind_me": "your reminder",
}


def wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent)


def show(message: dict, details: bool) -> None:
    kind = message["kind"]
    if kind == "email":
        print(
            "\n"
            + paint(f"━━━ {message['name']} ", BLUE, BOLD)
            + paint(f"({message['category']}, {message['sender']}) · {message['date']}", DIM)
        )
        print(f"    \"{paint(message['subject'], BOLD)}\"")
    elif kind == "user":
        return  # the user's own words are already on screen
    elif kind in ("note", "result"):
        print(paint(wrap(("✔ " if kind == "result" else "") + message["text"]), GREEN if kind == "result" else DIM))
    else:
        print("\n" + paint(f"  Wajo · {LABEL[kind]}", BOLD, COLOR[kind]))
        print(wrap(message["text"]))
        if message.get("draft"):
            print(paint(wrap("Draft: " + message["draft"][:300]), DIM))
        if details and message.get("details"):
            print(paint("    " + " · ".join(f"{k} {v}" for k, v in message["details"].items()), DIM))


def run(settings: dict, details: bool) -> None:
    session = build({**defaults(), **settings}["llm"])
    wajo, server = session.wajo, session.server
    folder = session_log.new_folder()
    print(
        paint("\nHi, I'm Wajo, your email assistant. ", BOLD) + f"You're {server.user_address}; {session.description}. "
        'Reply in your own words, like "yes", "archive it instead" or "label it research". Enter means yes.'
    )

    def say(text: str) -> None:
        for message in wajo.on_user(text, server.now):
            show(message, details)

    while True:
        email = session.emails.next(server)
        if not email:
            break
        email = server.receive(email)
        show(wajo.email_arrived(email), details)
        for message in wajo.on_email(email, server.now) + wajo.on_tick(server.now):
            show(message, details)
        while wajo.waiting():  # answer what Wajo asked, in your own words
            say(input(paint("  you › ", BOLD)))
        session_log.write(folder, wajo, session.description)
        command = input(paint("\n  [enter] next email · q quit · or say anything ", DIM)).strip()
        if command.lower() == "q":
            break
        while command:
            say(command)
            command = input(paint("  you › ", BOLD)).strip() if wajo.waiting() else ""
    session_log.write(folder, wajo, session.description)
    print("\n" + paint("Session summary", BOLD) + "\n" + wajo.audit.summary() + f"\nLogs: {folder}/")
