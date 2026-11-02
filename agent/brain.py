"""Wajo's judgment: what to do with a new email, what the user wants, what to say, how to word a reply.

Two brains with the same four methods:
- LLMBrain: the LLM set in .env, given the full context for every call.
- OfflineBrain: simple rules, so the app runs without an API key.
Neither can act: they only return tool calls. The gate decides what actually happens.
"""

import re
from typing import TYPE_CHECKING

from agent.llm import LLM
from agent.prompts import DECIDE, DRAFT, RESPOND, TRIAGE
from policy.models import Email
from policy.senders import other_party

if TYPE_CHECKING:
    from agent.wajo import Wajo

TRIAGE_KINDS = ["keep", "archive", "label", "trash", "mark_read", "forward", "unsubscribe"]


class LLMBrain:
    def __init__(self, llm: LLM):
        self.llm = llm

    def triage(self, wajo: "Wajo", email: Email, context: str) -> dict:
        return self.llm.complete_json(TRIAGE.format(user=wajo.mail.user_address, context=context), "Choose now.")

    def decide(self, wajo: "Wajo", text: str, context: str) -> list[dict]:
        calls = self.llm.complete_json(DECIDE.format(user=wajo.mail.user_address, context=context), text).get("calls")
        return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []

    def respond(self, wajo: "Wajo", facts: list[str], task: str, context: str) -> str:
        prompt = RESPOND.format(
            user=wajo.mail.user_address,
            context=context,
            task=task,
            facts="\n".join(f"- {f}" for f in facts) or "- nothing; no action was taken",
        )
        return str(self.llm.complete_json(prompt, "Write your message.").get("message") or " ".join(facts))

    def draft(self, wajo: "Wajo", email: Email, instructions: str, context: str) -> str:
        prompt = DRAFT.format(user=wajo.mail.user_address, context=context, instructions=instructions)
        body = self.llm.complete_json(prompt, "Write the reply.").get("body")
        return str(body).strip() if body else OfflineBrain().draft(wajo, email, instructions, context)


# --- offline rules ---

YES = {"", "y", "yes", "ok", "okay", "sure", "fine", "good", "go ahead", "do it", "yep", "looks good", "thanks"}
NO = {"n", "no", "nope", "don't", "dont", "stop"}
SEND = {"send", "send it", "send it please", "yes send it", "yes, send it"}
ALIASES = {"leave": "keep", "inbox": "keep", "delete": "trash", "read": "mark_read", "file": "label"}
TIMING = {
    "too early": "too_early",
    "early": "too_early",
    "too late": "too_late",
    "late": "too_late",
    "not needed": "not_needed",
    "no need": "not_needed",
}
REMIND = re.compile(
    r"remind(?:er)?(?: me)?(?: (?:in|for|about this|about it))? (tomorrow|next week|(\d+)[ -]days?)", re.I
)
REPLY = re.compile(r"\b(?:draft|write|reply|respond)\b.*?\b(?:saying|that|to say)\s+(.+)", re.I)
FIRST_PERSON = [
    ("manipulate you", "manipulate me"),
    ("so you did", "so I did"),
    ("wanted you to", "wanted me to"),
    ("You'll", "I'll"),
    ("You are", "I'm"),
    ("You ", "I "),
    ("the user's", "your"),
    ("The user", "You"),
    ("the user", "you"),
]
ABOUT_ME = re.compile(r"\b(i|i'm|i am|my|always|never|usually|prefer)\b", re.I)


def updated_note(wajo: "Wajo", text: str) -> str:
    """The earlier note this one updates, offline: one that starts with the same three words ("my favorite color")."""
    key = " ".join(re.sub(r"^(actually|now|btw)\s+", "", text.lower()).split()[:3])
    return next((n for n in wajo.profile.notes if key and key in n.lower()), "")


class OfflineBrain:
    def triage(self, wajo: "Wajo", email: Email, context: str) -> dict:
        sender, _ = other_party(email, wajo.mail)
        usual = wajo.gate.rates.usual_choice(sender, wajo.gate.kind_of(email))
        if usual:
            return {"kind": usual}
        return {"kind": "archive" if email.has_unsubscribe else "keep"}

    def decide(self, wajo: "Wajo", text: str, context: str) -> list[dict]:
        lowered = text.strip().lower()
        question = wajo.current_question()
        if question and lowered in TIMING:
            return [{"tool": "answer", "question": question, "reply": "yes", "timing": TIMING[lowered]}]
        if lowered in SEND:
            return [{"tool": "send_reply"}]
        if question and lowered in YES:
            return [{"tool": "answer", "question": question, "reply": "yes", "timing": "ok"}]
        if question and lowered in NO:
            return [{"tool": "answer", "question": question, "reply": "no"}]
        if lowered == "undo":
            return [{"tool": "undo"}]
        command = re.sub(r"^((no|nope|nah|actually|please|just)\b[,.!]?\s*)+", "", lowered).removesuffix(" instead")
        word, _, rest = command.partition(" ")
        kind = ALIASES.get(word, word)
        if kind in TRIAGE_KINDS and len(command.split()) <= 4:
            label = re.sub(r"^((it|with|as|under|to)\s+)+", "", rest).strip(" '\"") if kind == "label" else ""
            return [{"tool": "act", "kind": kind, "label": label}]
        folder = next((f for f in ("trash", "archived", "inbox", "sent", "drafts") if f.rstrip("sd") in lowered), None)
        if folder and re.search(r"\b(how many|what'?s in|show|list)\b", lowered):
            return [{"tool": "find", "folder": folder}]
        calls = []
        reply = REPLY.search(text)
        if reply:
            calls.append({"tool": "draft_reply", "instructions": reply.group(1)})
        remind = REMIND.search(lowered)
        if remind:
            word = remind.group(1)
            calls.append(
                {
                    "tool": "remind",
                    "days": 1 if word == "tomorrow" else 7 if word == "next week" else float(remind.group(2)),
                }
            )
        if lowered.startswith("send") or " send it" in lowered:
            calls.append({"tool": "send_reply"})
        if not calls and not text.strip().endswith("?") and ABOUT_ME.search(text) and len(text.split()) >= 3:
            calls.append({"tool": "remember", "note": text.strip(), "replaces": updated_note(wajo, text)})
        return calls

    def respond(self, wajo: "Wajo", facts: list[str], task: str, context: str) -> str:
        if facts:
            text = " ".join(f[:1].upper() + f[1:] + ("" if f.endswith((".", "?")) else ".") for f in facts)
            for old, new in FIRST_PERSON:
                text = text.replace(old, new)
            if task.startswith("Tell the user what the email is") and wajo.focus:
                line = next((s.strip() for s in wajo.mail.get(wajo.focus).body.splitlines() if s.strip()), "")
                text = f'It says: "{line[:160]}" {text}'
            return text
        return (
            "Sample a new email and I'll tell you what I'd do with it. You can also tell me how you work, "
            'like "I run the research group".'
        )

    def draft(self, wajo: "Wajo", email: Email, instructions: str, context: str) -> str:
        profile = wajo.profile.text()
        sign_off = re.search(r"(Best|Thanks|Cheers|Regards),? \w+", profile)
        name = re.search(r"\bname is (\w+)", profile, re.I)
        sign_off = sign_off.group(0) if sign_off else f"Best, {name.group(1)}" if name else "Best,"
        sentence = re.sub(r"^(saying|that|to say)\s+", "", instructions.strip().rstrip("."), flags=re.I)
        to = wajo.reply_to(email)
        return f"Hi {re.split(r'[._@-]', to)[0].title()},\n\n{sentence[:1].upper()}{sentence[1:]}.\n\n{sign_off}"
