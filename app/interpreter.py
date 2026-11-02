"""Turns the user's reply, in their own words, into structured intent.

It only extracts what the user wants. What Wajo then says back is built from what the agent
actually did (app/assistant.py), so it can never claim an action that didn't happen.
"""
import re
from typing import Optional

from agent.checks import ACTIONS
from agent.llm import LLM

PROMPT = """You are an email assistant. You asked the user something and they replied.
Your message: {question}
Extract what the user wants. Return JSON:
{{"decision": "yes" only if they clearly accept what you proposed or did; otherwise "no".
              Any objection, complaint or request for something different is "no".
  "instead": null, or the email action they want instead:
     {{"kind": one of {kinds}, "label": "label name or empty", "body": "reply text if they said what to write, else empty"}}
     Use draft_reply only if they explicitly ask you to write or draft a reply.
  "remind_in_days": null, or a number if they ask to be reminded about this email later (tomorrow = 1, next week = 7),
  "timing": null, or for a follow-up or reminder: "ok", "too_early" or "too_late",
  "remember": a lasting fact or preference about the user to remember (e.g. "Prefers short, simple replies"), or empty}}"""

CHAT = """You are Wajo, an email assistant, chatting with the user. They sent you a message outside any question.
What you already know about them:
{profile}
You cannot take any action from this message. Never say you will do something.
Return JSON:
{{"remember": a lasting fact or preference about the user or how they handle email that's worth remembering
              (rewrite it as a short note, e.g. "Runs the research group"), or empty if there's nothing to remember,
  "reply": one or two short, friendly sentences answering them. If you remembered something, say so briefly.}}"""

ABOUT_ME = re.compile(r"\b(i|i'm|i am|my|me|always|never|usually|prefer|don't|do not|please don't)\b", re.I)
REMIND = re.compile(r"remind(?:er)?(?: me)?(?: (?:in|for|about this))? (tomorrow|next week|(\d+)[ -]days?)", re.I)
OFFLINE_HELLO = ("Hi! Sample a new email and I'll tell you what I'd do with it. You can also tell me how you work, "
                 "like \"I run the research group\" or \"I never read conference invites\".")
YES = {"", "y", "yes", "ok", "okay", "sure", "fine", "good", "go ahead", "do it", "yep", "looks good", "thanks"}
NO = {"n", "no", "nope", "undo", "don't", "dont", "stop"}
ALIASES = {"reply": "draft_reply", "leave": "keep", "inbox": "keep", "delete": "trash", "read": "mark_read", "file": "label"}


def intent(decision: str = "no", instead: Optional[dict] = None, remind_in_days: Optional[float] = None,
           timing: Optional[str] = None, remember: str = "") -> dict:
    return {"decision": decision, "instead": instead, "remind_in_days": remind_in_days,
            "timing": timing, "remember": remember}


class Interpreter:
    def __init__(self, llm: Optional[LLM]):
        self.llm = llm    # None: offline, simple keyword rules

    def __call__(self, reply: str, question: str) -> dict:
        text = reply.strip().lower()
        quick = self.rules(text)
        if quick or self.llm is None:
            return quick or intent(remind_in_days=self.remind_days(text))
        result = self.llm.complete_json(PROMPT.format(question=question, kinds=", ".join(ACTIONS)), reply)
        instead = result.get("instead") or None
        if instead and instead.get("kind") not in ACTIONS:
            instead = None
        days = result.get("remind_in_days")
        return intent(decision="yes" if result.get("decision") == "yes" else "no", instead=instead,
                      remind_in_days=float(days) if isinstance(days, (int, float)) and days > 0 else None,
                      timing=result.get("timing") if result.get("timing") in ("ok", "too_early", "too_late") else None,
                      remember=str(result.get("remember") or "").strip())

    def chat(self, message: str, profile: str) -> dict:
        """A message outside any question: {"remember": note or "", "reply": text}."""
        if self.llm is None:
            if ABOUT_ME.search(message) and len(message.split()) >= 3:
                return {"remember": message.strip(), "reply": "Got it, I'll keep that in mind when I suggest what to do."}
            return {"remember": "", "reply": OFFLINE_HELLO}
        result = self.llm.complete_json(CHAT.format(profile=profile or "(nothing yet)"), message)
        return {"remember": str(result.get("remember") or "").strip(), "reply": str(result.get("reply") or "OK.")}

    @staticmethod
    def remind_days(text: str) -> Optional[float]:
        match = REMIND.search(text)
        if not match:
            return None
        return 1.0 if match.group(1) == "tomorrow" else 7.0 if match.group(1) == "next week" else float(match.group(2))

    @classmethod
    def rules(cls, text: str) -> Optional[dict]:
        """Short, unambiguous replies, answered without an LLM call."""
        timing = {"too early": "too_early", "early": "too_early", "too late": "too_late", "late": "too_late"}.get(text)
        if timing:
            return intent(decision="yes", timing=timing)
        if text in YES:
            return intent(decision="yes", timing="ok")
        if text in NO:
            return intent()
        command = re.sub(r"^((no|nope|nah|actually|please|just)\b[,.!]?\s*)+", "", text).removesuffix(" instead")
        word, _, rest = command.partition(" ")
        kind = ALIASES.get(word, word)
        if kind in ACTIONS:
            label = re.sub(r"^((it|with|as|under|to)\s+)+", "", rest).strip(" '\"") if kind == "label" else ""
            return intent(instead={"kind": kind, "label": label, "body": ""})
        if cls.remind_days(text):
            return intent(remind_in_days=cls.remind_days(text))
        return None
