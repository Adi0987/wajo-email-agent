"""What the user has told the agent about themselves and how they work.

Lives in memory for one session (the sandbox): nothing is written to disk.
The proposer reads all of it before suggesting an action. The safety checks never read it,
so a note can shape suggestions but can't unlock anything.
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
