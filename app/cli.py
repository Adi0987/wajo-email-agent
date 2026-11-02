"""`python3 wajo.py try`: the assistant in your terminal. Emails arrive one at a time; you answer."""
from collections import deque
from datetime import datetime

from agent.audit import AuditLog
from app.assistant import CHOICES, Assistant
from app.feed import build
from app.style import BLUE, BOLD, CYAN, DIM, GREEN, RED, YELLOW, paint

COLOR = {"ask": YELLOW, "notify": CYAN, "silent": GREEN, "escalate": RED, "nudge": BLUE, "reminder": BLUE,
         "result": GREEN, "note": DIM}
ICON = {"ask": "?", "notify": "✔", "silent": "✔", "escalate": "⚠", "nudge": "⏰", "reminder": "⏰",
        "result": "✔", "note": " "}


def show(message: dict, details: bool) -> None:
    kind = message["kind"]
    if kind == "email":
        print("\n" + paint(f"━━━ {message['name']} ", BLUE, BOLD)
              + paint(f"({message['category']}, {message['sender']}) · {message['date']}", DIM))
        print(f"    \"{paint(message['subject'], BOLD)}\"\n    {message['summary']}")
        return
    print(paint(f"\n  {ICON[kind]} {message['text']} ", BOLD, COLOR[kind]) + message.get("reason", ""))
    if message.get("why"):
        print(paint(f"    {message['why']}", DIM))
    if message.get("draft"):
        print(paint("    Draft: ", DIM) + message["draft"][:300])
    if details and message.get("details"):
        print(paint("    " + " · ".join(f"{k} {v}" for k, v in message["details"].items()), DIM))


def ask(message: dict) -> str:
    """Reads the user's answer and turns it into the assistant's reply words."""
    if message["kind"] == "ask":
        answer = input(paint(f"    OK? [y] yes · [n] no · or tell me what to do ({CHOICES}) ", DIM)).strip()
        return {"": "yes", "y": "yes", "yes": "yes", "n": "no", "no": "no"}.get(answer.lower(), answer)
    if message["kind"] == "notify":
        answer = input(paint(f"    [enter] fine · [u] undo · or tell me what to do instead ({CHOICES}) ", DIM)).strip()
        return {"": "fine", "u": "undo"}.get(answer.lower(), answer)
    answer = input(paint("    Good timing? [enter] yes · [e] too early · [l] too late ", DIM)).strip().lower()
    return {"e": "too_early", "l": "too_late"}.get(answer, "ok")


def run(persona: str, count: int, offline: bool, details: bool) -> None:
    agent, feed, narrator, source = build(persona, count, offline)
    assistant = Assistant(agent, narrator, AuditLog(f"runs/audit_{datetime.now():%Y%m%d_%H%M%S}.csv"))
    print(paint("\nHi, I'm your email assistant. ", BOLD) + f"Here come {source}. "
          "I'll ask before doing things until I learn how you like them handled.")
    for number, email in enumerate(feed, 1):
        print(paint(f"\n[{number}/{len(feed)}]", DIM), end="")
        queue = deque(assistant.deliver(email))
        while queue:
            message = queue.popleft()
            show(message, details)
            if message["open"]:
                queue.extend(assistant.answer(message["id"], ask(message)))
        if input(paint("\n  [enter] next email · q quit ", DIM)).strip().lower() == "q":
            break
    print("\n" + paint("Session summary", BOLD) + "\n" + assistant.audit.summary())
