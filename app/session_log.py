"""The only thing a session writes to disk: its logs, for auditing afterwards.

runs/<time>/decisions.csv    one row per decision: proposal, each check, final level, your response
runs/<time>/conversation.md  the whole thread, plus what the agent knows, has learned and has scheduled

Rewritten after every step, so nothing is lost if the app stops.
"""
from datetime import datetime
from pathlib import Path

from app.assistant import Assistant


def new_folder() -> Path:
    return Path("runs") / datetime.now().strftime("%Y%m%d_%H%M%S")


def write(folder: Path, assistant: Assistant, description: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "decisions.csv").write_text(assistant.audit.csv_text())
    (folder / "conversation.md").write_text(conversation(assistant, description))


def table(rows: list[dict], columns: list[tuple[str, str]]) -> list[str]:
    if not rows:
        return ["(nothing yet)", ""]
    return (["| " + " | ".join(title for _, title in columns) + " |", "|" + "---|" * len(columns)]
            + ["| " + " | ".join(str(row[key]).replace("|", "/") for key, _ in columns) + " |" for row in rows] + [""])


def conversation(assistant: Assistant, description: str) -> str:
    lines = [f"# Wajo session · {description}", f"Acting as {assistant.agent.mailbox.user_address}", "", "## Conversation", ""]
    for m in assistant.messages:
        kind = m["kind"]
        if kind == "email":
            body = " ".join(m["body"].split())[:600]
            lines += [f"### Email from {m['name']} <{m['sender']}> ({m['category']}) · {m['date']}",
                      f"**Subject:** {m['subject']}", "", f"> {body}", ""]
        elif kind == "user":
            lines += [f"**You:** {m['text']}", ""]
        elif kind == "note":
            lines += [f"**Wajo:** {m['text']}", ""]
        elif kind == "result":
            lines += [f"✔ {m['text']}", ""]
        else:
            lines += [f"**Wajo ({kind}):** {m['text']}"]
            if m.get("draft"):
                lines.append(f"_Draft: {m['draft']}_")
            if m.get("details"):
                d = m["details"]
                lines.append(f"_Checks: action {d['action']} · email {d['email']} · learned {d['learned']} · {d['rate']}_")
            lines.append("")
            if m.get("answer"):
                lines += [f"**You:** {m['answer']}", ""]
    learned = assistant.learned()
    lines += ["## What Wajo knows about you", ""] + ([f"- {n}" for n in assistant.profile.notes] or ["(nothing yet)"]) + [""]
    lines += ["## Learned, per sender", ""] + table(learned["senders"],
              [("who", "Sender"), ("action", "Action"), ("approved", "✓"), ("rejected", "✗"), ("level", "Now")])
    lines += ["## Learned, per kind of sender", ""] + table(learned["groups"],
              [("who", "Kind"), ("action", "Action"), ("approved", "✓"), ("rejected", "✗"), ("rate", "Rate")])
    lines += ["## Learned timing", ""] + table(assistant.timing(),
              [("who", "Kind"), ("follow_up", "Follow up after"), ("reminder", "Remind")])
    lines += ["## Scheduled", ""] + table(assistant.scheduled(), [("at", "When"), ("what", "What")])
    lines += ["## Summary", "", assistant.audit.summary(), ""]
    return "\n".join(lines)
