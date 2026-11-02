"""What Wajo remembers within a session (the sandbox; nothing is written to disk).

- Profile: what the user has told Wajo about themselves and how they work.
- Corrections: past decisions and how the user responded, recalled for similar emails so the
  agent can follow what the user actually did before, not just a count.
"""


class Profile:
    def __init__(self):
        self.notes: list[str] = []

    def add(self, note: str) -> None:
        note = note.strip()
        if note and note not in self.notes:
            self.notes.append(note)

    def replace(self, text: str) -> None:
        """Replaces every note with the lines of `text`, one note per line."""
        self.notes = [line.strip("-• ").strip() for line in text.splitlines() if line.strip("-• ").strip()]

    def text(self) -> str:
        return "\n".join(f"- {note}" for note in self.notes)


def describe_feedback(item: dict) -> str:
    proposed = f"label '{item['label']}'" if item["proposed"] == "label" and item["label"] else item["proposed"]
    if item["chosen"]:
        verdict = f"the user said no and chose {item['chosen']}"
    else:
        verdict = "the user agreed" if item["approved"] else "the user said no"
    return f"\"{item['subject']}\" from {item['sender']} ({item['kind']}): I proposed {proposed}; {verdict}."


def similar_corrections(history: list[dict], sender: str, kind: str, limit: int = 6) -> list[str]:
    """Past feedback on emails from this sender first, then on this kind of email, most recent first."""
    same_sender = [h for h in reversed(history) if h["sender"] == sender]
    same_kind = [h for h in reversed(history) if h["kind"] == kind and h["sender"] != sender]
    return [describe_feedback(h) for h in (same_sender + same_kind)[:limit]]
