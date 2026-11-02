"""Turns the user's reply, in their own words, into feedback the agent understands."""
import re
from typing import Optional

from agent.checks import ACTIONS
from agent.llm import LLM

PROMPT = """You are an email assistant. You asked the user something and they replied.
Your message: {question}
Interpret their reply. Return JSON:
{{"decision": "yes" or "no",
  "instead": null, or the action they want instead:
     {{"kind": one of {kinds}, "label": "label name or empty", "body": "reply text if they said what to write, else empty"}},
  "timing": null, or for a follow-up or reminder: "ok", "too_early" or "too_late",
  "acknowledgement": one short, natural sentence confirming what you'll do}}
"Do X instead" means decision "no" with instead set. Approving your suggestion means decision "yes"."""

YES = {"", "y", "yes", "ok", "okay", "sure", "fine", "good", "go ahead", "do it", "yep", "looks good", "thanks"}
NO = {"n", "no", "nope", "undo", "don't", "dont", "stop"}
ALIASES = {"reply": "draft_reply", "leave": "keep", "inbox": "keep", "delete": "trash", "read": "mark_read", "file": "label"}


class Interpreter:
    def __init__(self, llm: Optional[LLM]):
        self.llm = llm    # None: offline, simple keyword rules

    def __call__(self, reply: str, question: str) -> dict:
        text = reply.strip().lower()
        quick = self.rules(text)
        if quick or self.llm is None:
            return quick or {"decision": "no", "instead": None, "timing": None,
                             "acknowledgement": "I didn't quite get that, so I'll take it as a no. "
                                                "You can say things like \"archive it\" or \"label it research\"."}
        result = self.llm.complete_json(PROMPT.format(question=question, kinds=", ".join(ACTIONS)), reply)
        instead = result.get("instead") or None
        if instead and instead.get("kind") not in ACTIONS:
            instead = None
        return {"decision": "yes" if result.get("decision") == "yes" else "no", "instead": instead,
                "timing": result.get("timing") if result.get("timing") in ("ok", "too_early", "too_late") else None,
                "acknowledgement": str(result.get("acknowledgement", ""))}

    @staticmethod
    def rules(text: str) -> Optional[dict]:
        """Short, unambiguous replies, answered without an LLM call."""
        timing = {"too early": "too_early", "early": "too_early", "too late": "too_late", "late": "too_late"}.get(text)
        if timing:
            return {"decision": "yes", "instead": None, "timing": timing, "acknowledgement": "Noted, I'll adjust the timing."}
        if text in YES:
            return {"decision": "yes", "instead": None, "timing": "ok", "acknowledgement": ""}
        if text in NO:
            return {"decision": "no", "instead": None, "timing": None, "acknowledgement": ""}
        word, _, rest = text.removesuffix(" instead").partition(" ")
        kind = ALIASES.get(word, word)
        if kind in ACTIONS:
            label = re.sub(r"^((it|with|as|under|to)\s+)+", "", rest).strip(" '\"") if kind == "label" else ""
            return {"decision": "no", "instead": {"kind": kind, "label": label, "body": ""}, "timing": None,
                    "acknowledgement": ""}
        return None
