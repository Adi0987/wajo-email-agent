"""Turns whatever the user writes into structured intent, given the conversation's context.

It only extracts what the user wants. What Wajo does is decided in code (app/assistant.py), and
what Wajo says back is built from what actually happened, so it can never claim an action it didn't take.
"""
import re
from typing import Optional

from agent.llm import LLM

TRIAGE = ["keep", "archive", "label", "trash", "mark_read", "forward", "unsubscribe"]

TURN = """You are Wajo, an email assistant working in the user's mailbox. You can archive, label, trash, keep,
mark read, forward, unsubscribe, write reply drafts, send replies (after the user approves), and set reminders.

{context}

The user just wrote the message below. Extract what they want. Return JSON:
{{"answer": "yes" if they accept your open question, "no" if they refuse it or object, null if they don't address it,
  "instead": null, or a different action for this email instead of your proposal:
             {{"kind": one of {triage}, "label": "label name or empty", "to": []}},
  "reply": null, or {{"instructions": "what the reply should say"}} if they want a reply written or rewritten,
  "send": true only if they want the current draft sent now, else false,
  "remind_in_days": null, or a number if they want a reminder about this email (tomorrow = 1),
  "timing": null, or "ok", "too_early" or "too_late" for a follow-up or reminder,
  "remember": a lasting fact or preference about the user worth remembering, as a short note, or empty,
  "question": null, or the question they asked you}}"""

ANSWER = """You are Wajo, an email assistant. Answer the user's message in 1 to 3 short, friendly sentences,
using only these facts. You can't take any action in this reply, so never say you did or will do something.

{context}"""

YES = {"", "y", "yes", "ok", "okay", "sure", "fine", "good", "go ahead", "do it", "yep", "looks good", "thanks",
       "send", "send it", "send it please", "yes send it"}
NO = {"n", "no", "nope", "undo", "don't", "dont", "stop"}
ALIASES = {"leave": "keep", "inbox": "keep", "delete": "trash", "read": "mark_read", "file": "label"}
REMIND = re.compile(r"remind(?:er)?(?: me)?(?: (?:in|for|about this|about it))? (tomorrow|next week|(\d+)[ -]days?)", re.I)
REPLY = re.compile(r"\b(?:draft|write|reply|respond)\b.*?\b(?:saying|that|to say)\s+(.+)", re.I)
ABOUT_ME = re.compile(r"\b(i|i'm|i am|my|always|never|usually|prefer)\b", re.I)
TIMING = {"too early": "too_early", "early": "too_early", "too late": "too_late", "late": "too_late"}


def intent(**fields) -> dict:
    base = {"answer": None, "instead": None, "reply": None, "send": False, "remind_in_days": None,
            "timing": None, "remember": "", "question": None}
    return {**base, **fields}


class Interpreter:
    def __init__(self, llm: Optional[LLM]):
        self.llm = llm    # None: offline, simple rules

    def turn(self, text: str, context: str, has_question: bool) -> dict:
        quick = self.rules(text.strip().lower(), has_question)
        if quick or self.llm is None:
            return quick or self.offline(text)
        result = self.llm.complete_json(TURN.format(context=context, triage=", ".join(TRIAGE)), text)
        instead = result.get("instead") or None
        if instead and instead.get("kind") not in TRIAGE:
            instead = None
        reply = result.get("reply") or None
        days = result.get("remind_in_days")
        return intent(
            answer=result.get("answer") if result.get("answer") in ("yes", "no") else None,
            instead=instead,
            reply={"instructions": str(reply.get("instructions", ""))} if isinstance(reply, dict) else None,
            send=result.get("send") is True,
            remind_in_days=float(days) if isinstance(days, (int, float)) and days > 0 else None,
            timing=result.get("timing") if result.get("timing") in TIMING.values() or result.get("timing") == "ok" else None,
            remember=str(result.get("remember") or "").strip(),
            question=result.get("question") or None)

    def answer(self, text: str, context: str) -> str:
        """A reply grounded in the facts in `context`, for questions and small talk."""
        if self.llm is None:
            return ("Hi! Sample a new email and I'll tell you what I'd do with it. You can also tell me how you work, "
                    "like \"I run the research group\".")
        return str(self.llm.complete_json(ANSWER.format(context=context) + '\nReturn JSON: {"reply": "..."}', text)
                   .get("reply") or "OK.")

    @staticmethod
    def remind_days(text: str) -> Optional[float]:
        match = REMIND.search(text)
        if not match:
            return None
        return 1.0 if match.group(1).lower() == "tomorrow" else 7.0 if match.group(1).lower() == "next week" \
            else float(match.group(2))

    @classmethod
    def rules(cls, text: str, has_question: bool) -> Optional[dict]:
        """Short, unambiguous messages, understood without an LLM call."""
        if text in TIMING:
            return intent(answer="yes", timing=TIMING[text])
        if has_question and text in YES:
            return intent(answer="yes", timing="ok", send=text.startswith("send") or text.startswith("yes send"))
        if has_question and text in NO:
            return intent(answer="no")
        command = re.sub(r"^((no|nope|nah|actually|please|just)\b[,.!]?\s*)+", "", text).removesuffix(" instead")
        word, _, rest = command.partition(" ")
        kind = ALIASES.get(word, word)
        if kind in TRIAGE and len(command.split()) <= 4:
            label = re.sub(r"^((it|with|as|under|to)\s+)+", "", rest).strip(" '\"") if kind == "label" else ""
            return intent(answer="no", instead={"kind": kind, "label": label, "to": []})
        return None

    def offline(self, text: str) -> dict:
        """Longer messages without an LLM: replies, sends, reminders, questions, facts about the user."""
        lowered = text.lower()
        reply = REPLY.search(text)
        found = intent(remind_in_days=self.remind_days(lowered),
                       reply={"instructions": reply.group(1)} if reply else None,
                       send=lowered.startswith("send") or " send it" in lowered,
                       answer="no" if re.match(r"^(no|nope|don't|do not)\b", lowered) else None)
        if lowered.rstrip("?").strip().endswith("?") or text.strip().endswith("?"):
            found["question"] = text
        if not any(found[k] for k in ("remind_in_days", "reply", "send", "question", "answer")) \
                and ABOUT_ME.search(text) and len(text.split()) >= 3:
            found["remember"] = text.strip()
        return found
