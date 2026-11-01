"""Records every decision and the user's response, for review after a session.

One CSV row per decision, saved after every change so nothing is lost on quit.
"""
import csv
from collections import Counter
from pathlib import Path

from agent.models import Email, Level

FIELDS = ["time", "email_id", "from", "category", "subject", "proposed", "to",
          "action_check", "email_check", "learned", "level",
          "classifier_money", "classifier_injection", "user_response"]


class AuditLog:
    def __init__(self, path: str):
        self.path = Path(path)
        self.rows: list[dict] = []

    def decision(self, entry: dict, email: Email, category: str, labels: dict) -> None:
        action, checks = entry["action"], entry["checks"]
        self.rows.append({
            "time": f"{entry['at']:%Y-%m-%d %H:%M}", "email_id": email.id, "from": email.sender,
            "category": category, "subject": email.subject, "proposed": action.kind, "to": " ".join(action.to),
            "action_check": checks["action"].name, "email_check": checks["email"].name,
            "learned": checks["learned"].name, "level": entry["level"].name,
            "classifier_money": labels.get("money", False), "classifier_injection": labels.get("injection", False),
            "user_response": "",
        })
        self.save()

    def response(self, email_id: str, text: str) -> None:
        """Attach the user's response to the latest decision on this email."""
        for row in reversed(self.rows):
            if row["email_id"] == email_id:
                row["user_response"] = f"{row['user_response']}; {text}" if row["user_response"] else text
                break
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)

    def summary(self) -> str:
        if not self.rows:
            return "No decisions."
        levels = Counter(row["level"] for row in self.rows)
        half = len(self.rows) // 2

        def ask_rate(rows):
            return f"{100 * sum(r['level'] == Level.ASK.name for r in rows) / len(rows):.0f}%" if rows else "–"

        responses = Counter(row["user_response"].split(",")[0] for row in self.rows if row["user_response"])
        return "\n".join([
            f"Decisions: {len(self.rows)}  ·  " + "  ".join(f"{level.name}: {levels[level.name]}" for level in Level),
            f"Ask rate: first half {ask_rate(self.rows[:half])}, second half {ask_rate(self.rows[half:])}",
            "Your responses: " + ", ".join(f"{text} {n}" for text, n in responses.most_common()),
            f"Full log: {self.path}",
        ])
