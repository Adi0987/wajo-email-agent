"""The tools Wajo can call when the user writes. Each returns facts: what actually happened, in words,
read from the gate's outcome. Wajo's message is written from these facts, so it can't claim
something that didn't happen.

Every change goes through the gate. Wajo never sends on its own: a reply becomes a question that shows
the user the exact text, and it goes out only when they say yes.
"""

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from policy.checks import USER_ONLY, is_external
from policy.gate import Outcome
from policy.models import Action, Level

if TYPE_CHECKING:
    from agent.wajo import Wajo

TRIAGE = {"keep", "archive", "label", "trash", "mark_read", "forward", "unsubscribe"}


def describe(action: Action) -> str:
    target = f" to {', '.join(action.to)}" if action.to else ""
    return {
        "keep": "leave it in the inbox",
        "archive": "archive it",
        "unsubscribe": "unsubscribe the user",
        "draft_reply": "save a draft reply",
        "send": f"send the reply{target}",
        "forward": f"forward it{target}",
        "mark_read": "mark it read",
        "trash": "move it to the trash",
        "label": f"label it '{action.label}'" if action.label else "label it",
    }.get(action.kind, action.kind)


def outcome_fact(outcome: Outcome, requested: bool = False) -> str:
    """What the gate did with an action, as one sentence."""
    what, level = describe(outcome.action), outcome.level
    if level == Level.ESCALATE and requested and outcome.outside:
        return (
            f"You couldn't {what}: {', '.join(outcome.action.to)} is outside this thread and the user's contacts, "
            f"and you never send to new outside addresses, even when asked. The user can do it "
            f"themselves."
        )
    if level == Level.ESCALATE and requested:
        return (
            f"You couldn't {what}: this email is flagged as phishing or manipulation, so nothing from it is "
            f"forwarded or sent anywhere new, even when the user asks. The user can do it themselves."
        )
    if level == Level.ESCALATE:
        return (
            f"The email looks like phishing or an attempt to manipulate you, so you did nothing (it wanted you to "
            f"{what}). Suggest checking with the sender directly."
        )
    if level == Level.ASK and not outcome.executed:
        shown = " The exact text is shown to the user." if outcome.action.body else ""
        return f"You are asking the user whether to {what}.{shown}"
    if not outcome.executed:
        return f"You tried to {what}, but the mail server refused it."
    if outcome.action.kind == "keep":
        return "You left it in the inbox for the user."
    if level == Level.NOTIFY:
        return f"You went ahead: {what}. The user can undo it."
    return f"You went ahead quietly: {what}."


def action_from(call: dict, email_id: str) -> Optional[Action]:
    spec = call if "kind" in call else (call.get("instead") or {})
    if spec.get("kind") not in TRIAGE:
        return None
    return Action(spec["kind"], email_id, label=str(spec.get("label") or ""), to=tuple(spec.get("to") or ()))


def run(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    tool = TOOLS.get(call.get("tool"))
    return tool(wajo, call, now) if tool else []


def answer(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    asked = re.sub(r"\D", "", str(call.get("question") or ""))
    qid = int(asked) if asked and int(asked) in wajo.questions else wajo.current_question()
    if qid is None:
        return []
    notice = wajo.close(qid)
    gate, email_id = wajo.gate, notice.email_id
    wajo.focus = email_id
    if notice.kind in ("nudge", "reminder"):
        verdict = call.get("timing") if call.get("timing") in ("ok", "too_early", "too_late", "not_needed") else "ok"
        days = call.get("days") if isinstance(call.get("days"), (int, float)) and call.get("days") > 0 else None
        setting = gate.timing_feedback(notice, verdict, days)
        wajo.log_response(email_id, f"{notice.kind} timing {verdict.replace('_', ' ')}")
        return [
            {
                "ok": "The user said the timing was right.",
                "too_early": "Noted: that was too early.",
                "too_late": "Noted: that was too late.",
                "not_needed": "Noted: the user doesn't want follow-ups like this.",
            }[verdict]
            + (f" {setting}" if setting else "")
        ]
    instead = action_from(call, email_id)
    agreed = call.get("reply") == "yes" and not instead
    if instead and instead.kind == notice.action.kind and instead.label == notice.action.label:
        instead, agreed = None, True  # "archive it" when you proposed archiving is a yes
    what = describe(notice.action)
    if notice.kind == "ask" and agreed:
        done = gate.approve(notice, now)
        wajo.log_response(email_id, "approved")
        return [f"Done: {what}." if done else f"You couldn't {what}: it's no longer allowed."]
    if notice.kind == "notify" and agreed:
        gate.confirm(notice)
        wajo.log_response(email_id, "confirmed")
        return [f"The user confirmed that was right ({what})."]
    chosen = instead.kind if instead else None
    if notice.kind == "ask":
        gate.reject(notice, chosen=chosen)
        wajo.log_response(email_id, f"rejected, wanted {chosen}" if chosen else "rejected")
        facts = [f"You won't {what}."]
    else:
        gate.undo(notice.action, chosen=chosen)
        wajo.log_response(email_id, f"undone, wanted {chosen}" if chosen else "undone")
        facts = [] if notice.action.kind == "keep" else [f"Undone: {what}."]
    if instead:
        facts.append(requested(wajo, instead, now))
    return facts


def requested(wajo: "Wajo", action: Action, now: datetime) -> str:
    """Runs something the user asked for. Anything that leaves the mailbox becomes a question."""
    outcome = wajo.gate.request(action, now)
    if action.kind == "keep":
        return "Left it in the inbox, as the user asked."
    if is_external(action.kind):
        return outcome_fact(outcome, requested=True)
    if outcome.executed:
        return f"Done, as the user asked: {describe(action)}."
    return f"The safety checks don't allow you to {describe(action)} for this email."


def act(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    email_id = wajo.email_for(call)
    action = action_from(call, email_id) if email_id else None
    if not action:
        return []
    waiting = next(
        (
            q
            for q, n in wajo.questions.items()
            if n.email_id == email_id
            and n.action
            and n.action.kind not in USER_ONLY
            and (n.kind == "ask" or (n.kind == "notify" and not is_external(action.kind)))
        ),
        None,
    )
    if waiting is not None:  # a different action on an email you asked about is an answer; asking for an extra
        # outward one (unsubscribe, forward) after something was done isn't a correction
        return answer(
            wajo,
            {
                "question": waiting,
                "reply": "no",
                "instead": {"kind": action.kind, "label": action.label, "to": list(action.to)},
            },
            now,
        )
    return [requested(wajo, action, now)]


def undo(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    email_id = wajo.email_for(call)
    done = [
        e["action"]
        for e in wajo.gate.executor.log
        if e["executed"]
        and e["action"].email_id == email_id
        and e["action"].kind not in ("keep", "send", "forward", "unsubscribe")
    ]
    if not done:
        return ["There was nothing you could undo on that email."]
    for qid in [q for q, n in wajo.questions.items() if n.email_id == email_id and n.kind == "notify"]:
        wajo.close(qid)
    undone = wajo.gate.undo(done[-1])
    wajo.log_response(email_id, "undone")
    return [f"Undone: {describe(done[-1])}." if undone else f"You couldn't undo that ({describe(done[-1])})."]


def draft_reply(wajo: "Wajo", call: dict, now: datetime, unless_same: str = "") -> list[str]:
    """Writes the reply and asks to send it. With `unless_same`, does nothing if the new draft is that text."""
    email_id = wajo.email_for(call)
    if not email_id:
        return []
    instructions = str(call.get("instructions") or "")
    email = wajo.mail.get(email_id)
    body = wajo.brain.draft(wajo, email, instructions, draft_context(wajo, email))
    if unless_same and body.strip() == unless_same.strip():
        return []
    wajo.instructions[email_id] = instructions
    wajo.settle(email_id)
    for qid in [
        q for q, n in wajo.questions.items() if n.email_id == email_id and n.kind == "ask" and n.action.kind == "send"
    ]:
        wajo.gate.executor.reject(wajo.close(qid).approval_id)  # replaced by the new draft
    if not wajo.gate.request(Action("draft_reply", email_id, body=body), now).executed:
        return ["The safety checks don't allow a reply to this email."]
    to = wajo.reply_to(email)
    outcome = wajo.gate.request(Action("send", email_id, to=(to,), body=body), now)
    return [
        f"You wrote a draft reply to {to} and saved it. Its exact text: \"{' '.join(body.split())}\"",
        outcome_fact(outcome, requested=True),
    ]


def draft_context(wajo: "Wajo", email) -> str:
    """Only what a reply needs: who it's to and what it's about. The email's text is left out on purpose, so the
    draft can only say what the user asked it to say."""
    draft = wajo.mail.status(email.id).get("draft")
    current = f"The current draft, which the user may be asking you to change:\n{draft}\n" if draft else ""
    return (
        f'Replying to {wajo.reply_to(email)} about "{email.subject}".\n{current}'
        f"What the user has told you about themselves:\n{wajo.profile.text() or '(nothing yet)'}"
    )


def send_reply(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    email_id = wajo.email_for(call)
    if not email_id:
        return []
    waiting = next(
        (
            q
            for q, n in wajo.questions.items()
            if n.email_id == email_id and n.kind == "ask" and n.action.kind == "send"
        ),
        None,
    )
    if waiting is not None:
        return answer(wajo, {"question": waiting, "reply": "yes"}, now)
    draft = wajo.mail.status(email_id).get("draft")
    if draft:
        email = wajo.mail.get(email_id)
        return [
            outcome_fact(
                wajo.gate.request(Action("send", email_id, to=(wajo.reply_to(email),), body=draft), now), requested=True
            )
        ]
    sent = [e for e in wajo.mail.thread(wajo.mail.get(email_id).thread_id) if e.sender == wajo.mail.user_address]
    if sent:
        return [f"You already sent a reply on {sent[-1].sent_at:%a %b %d}; there's no other draft."]
    return ["There's no draft for this email yet; the user can tell you what to say."]


def remind(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    email_id = wajo.email_for(call)
    days = call.get("days")
    if not email_id or not isinstance(days, (int, float)) or days <= 0:
        return []
    when = now + timedelta(days=days)
    wajo.settle(email_id)
    wajo.gate.remind(email_id, when)
    return [f"You'll remind the user about it on {when:%a %b %d}."]


def remember(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    note = str(call.get("note") or "").strip()
    if not note:
        return []
    replaces = str(call.get("replaces") or "").strip().lower()
    dropped = [n for n in wajo.profile.notes if replaces and replaces in n.lower()]
    wajo.profile.notes = [n for n in wajo.profile.notes if n not in dropped]
    wajo.profile.add(note)
    facts = [
        f"You'll remember: {note.rstrip('.')}"
        + (f" (instead of: {'; '.join(dropped)})." if dropped else ".")
        + " It shapes what you suggest; you still ask before acting on your own until the user has okayed that"
        " kind of action a few times."
    ]
    for qid, notice in list(wajo.questions.items()):  # a waiting draft is rewritten if what you learned changes it
        if notice.kind == "ask" and notice.action.kind == "send" and notice.email_id in wajo.instructions:
            facts += draft_reply(
                wajo,
                {"email": notice.email_id, "instructions": wajo.instructions[notice.email_id]},
                now,
                unless_same=notice.action.body,
            )
    return facts


def cancel(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    email_id = wajo.email_for(call)
    if not email_id:
        return []
    cancelled = wajo.gate.cancel_scheduled(email_id)
    thread = {e.id for e in wajo.mail.thread(wajo.mail.get(email_id).thread_id)}
    for qid in [q for q, n in wajo.questions.items() if n.email_id in thread and n.kind in ("nudge", "reminder")]:
        wajo.close(qid)  # a follow-up that already came up no longer needs an answer
        cancelled += 1
    subject = wajo.mail.get(email_id).subject
    return [
        (
            f'Cancelled {cancelled} scheduled item(s) for "{subject}"; nothing more is scheduled for it.'
            if cancelled
            else f'Nothing was scheduled for "{subject}".'
        )
    ]


def find(wajo: "Wajo", call: dict, now: datetime) -> list[str]:
    folder = call.get("folder") if call.get("folder") in ("inbox", "archived", "trash", "sent", "drafts") else "all"
    found = wajo.mail.search(folder, query=str(call.get("text") or ""), sender=str(call.get("sender") or ""))
    lines = [
        f"{e['date'][:10]} {('to ' + ', '.join(e['to'])) if e['folder'] == 'sent' else e['from']}: "
        f"\"{e['subject']}\" ({e['folder']}{', labeled ' + ', '.join(e['labels']) if e['labels'] else ''})"
        for e in found["emails"]
    ]
    where = "the whole mailbox" if folder == "all" else f"the {folder}"
    shown = f" (showing the newest {len(lines)})" if found["total"] > len(lines) else ""
    return [
        f"Looked in {where}: {found['total']} matching email(s){shown}." + ("\n" + "\n".join(lines) if lines else "")
    ]


TOOLS = {
    "answer": answer,
    "act": act,
    "undo": undo,
    "draft_reply": draft_reply,
    "send_reply": send_reply,
    "remind": remind,
    "remember": remember,
    "cancel": cancel,
    "find": find,
}
