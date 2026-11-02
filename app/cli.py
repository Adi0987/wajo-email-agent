"""`python3 wajo.py try`: the assistant in your terminal. Emails arrive one at a time; reply in your own words."""
import textwrap
from collections import deque

from agent.audit import AuditLog
from app.assistant import Assistant
from app.feed import build, defaults
from app.style import BLUE, BOLD, CYAN, DIM, GREEN, RED, YELLOW, paint

COLOR = {"ask": YELLOW, "notify": CYAN, "silent": GREEN, "escalate": RED, "nudge": BLUE, "reminder": BLUE}
LABEL = {"ask": "asking", "notify": "did it, told you", "silent": "did it quietly", "escalate": "escalated",
         "nudge": "follow-up", "reminder": "reminder"}


def wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent)


def show(message: dict, details: bool) -> None:
    kind = message["kind"]
    if kind == "email":
        print("\n" + paint(f"━━━ {message['name']} ", BLUE, BOLD)
              + paint(f"({message['category']}, {message['sender']}) · {message['date']}", DIM))
        print(f"    \"{paint(message['subject'], BOLD)}\"")
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
    s = {**defaults(), **settings}
    session = build(s["source"], s["persona"], s["count"], s["llm"])
    assistant = Assistant(session.agent, session.llm, session.profile, AuditLog())
    print(paint("\nHi, I'm Wajo, your email assistant. ", BOLD) + f"Here come {session.description}. "
          "Reply in your own words, like \"yes\", \"archive it instead\" or \"label it research\". Enter means yes.")
    for number, email in enumerate(session.feed, 1):
        print(paint(f"\n[{number}/{len(session.feed)}]", DIM), end="")
        queue = deque(assistant.deliver(email))
        while queue:
            message = queue.popleft()
            show(message, details)
            if message["open"]:
                queue.extend(assistant.answer(message["id"], input(paint("  you › ", BOLD))))
        command = input(paint("\n  [enter] next email · q quit · or tell me something about how you work ", DIM)).strip()
        if command.lower() == "q":
            break
        if command:
            for message in assistant.tell(command):
                show(message, details)
    print("\n" + paint("Session summary", BOLD) + "\n" + assistant.audit.summary())
