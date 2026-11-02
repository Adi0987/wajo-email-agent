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
  "remember": a lasting fact or preference about the user to remember (e.g. "Conference invites are noise unless I'm speaking"), or empty,
  "acknowledgement": one short, natural sentence confirming what you'll do}}
"Do X instead" means decision "no" with instead set. Approving your suggestion means decision "yes"."""

CHAT = """You are Wajo, an email assistant, chatting with the user. They sent you a message outside any question.
What you already know about them:
{profile}
Return JSON:
{{"remember": a lasting fact or preference about the user or how they handle email that's worth remembering
              (rewrite it as a short note, e.g. "Runs the research group"), or empty if there's nothing to remember,
  "reply": one or two short, friendly sentences answering them. If you remembered something, say so briefly.}}"""

ABOUT_ME = re.compile(r"\b(i|i'm|i am|my|me|always|never|usually|prefer|don't|do not|please don't)\b", re.I)
OFFLINE_HELLO = ("Hi! Sample a new email and I'll tell you what I'd do with it. You can also tell me how you work, "
                 "like \"I run the research group\" or \"I never read conference invites\".")

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
            return quick or {"decision": "no", "instead": None, "timing": None, "remember": "",
                             "acknowledgement": "I didn't quite get that, so I'll take it as a no. "
                                                "You can say things like \"archive it\" or \"label it research\"."}
        result = self.llm.complete_json(PROMPT.format(question=question, kinds=", ".join(ACTIONS)), reply)
        instead = result.get("instead") or None
        if instead and instead.get("kind") not in ACTIONS:
            instead = None
        return {"decision": "yes" if result.get("decision") == "yes" else "no", "instead": instead,
                "timing": result.get("timing") if result.get("timing") in ("ok", "too_early", "too_late") else None,
                "remember": str(result.get("remember") or ""),
                "acknowledgement": str(result.get("acknowledgement", ""))}

    def chat(self, message: str, profile: str) -> dict:
        """A message outside any question: {"remember": note or "", "reply": text}."""
        if self.llm is None:
            if ABOUT_ME.search(message) and len(message.split()) >= 3:
                return {"remember": message.strip(), "reply": "Got it, I'll keep that in mind when I suggest what to do."}
            return {"remember": "", "reply": OFFLINE_HELLO}
        result = self.llm.complete_json(CHAT.format(profile=profile or "(nothing yet)"), message)
        return {"remember": str(result.get("remember") or "").strip(), "reply": str(result.get("reply") or "OK.")}

    @staticmethod
    def rules(text: str) -> Optional[dict]:
        """Short, unambiguous replies, answered without an LLM call."""
        timing = {"too early": "too_early", "early": "too_early", "too late": "too_late", "late": "too_late"}.get(text)
        if timing:
            return {"decision": "yes", "instead": None, "timing": timing, "acknowledgement": "Noted, I'll adjust the timing.", "remember": ""}
        if text in YES:
            return {"decision": "yes", "instead": None, "timing": "ok", "acknowledgement": "", "remember": ""}
        if text in NO:
            return {"decision": "no", "instead": None, "timing": None, "acknowledgement": "", "remember": ""}
        command = re.sub(r"^((no|nope|nah|actually|please|just)\b[,.!]?\s*)+", "", text).removesuffix(" instead")
        word, _, rest = command.partition(" ")
        kind = ALIASES.get(word, word)
        if kind in ACTIONS:
            label = re.sub(r"^((it|with|as|under|to)\s+)+", "", rest).strip(" '\"") if kind == "label" else ""
            return {"decision": "no", "instead": {"kind": kind, "label": label, "body": ""}, "timing": None,
                    "acknowledgement": "", "remember": ""}
        return None
