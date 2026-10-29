"""LLM step 2: label the email. Sees only the email, never the proposed action."""
from datetime import datetime
from typing import Optional

from agent.llm import LLM
from agent.models import Email
from agent.prompts import CLASSIFY, format_email


class Classifier:
    def __init__(self, llm: LLM):
        self.llm = llm

    def __call__(self, email: Email) -> dict:
        reply = self.llm.complete_json(CLASSIFY, format_email(email))
        return {
            "money": reply.get("money") is True,
            "injection": reply.get("injection") is True,
            "deadline": parse_date(reply.get("deadline")),
        }


def parse_date(value) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").replace(hour=9)
    except ValueError:
        return None
