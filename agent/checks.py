"""The three checks. The final level is the most cautious of them.

Checks 1 and 2 are the safety floor: fixed rules, no learned state.
Check 3 (learned) comes from agent.rates.
"""
from agent.models import Flags, Level

# action: (leaves the mailbox, can't be undone)
ACTIONS = {
    "label":       (False, False),
    "archive":     (False, False),
    "mark_read":   (False, False),
    "trash":       (False, False),
    "draft_reply": (False, False),
    "send":        (True, True),
    "forward":     (True, True),
    "unsubscribe": (True, True),
}


def is_external(kind: str) -> bool:
    return ACTIONS[kind][0]


def action_check(kind: str) -> Level:
    """Check 1: what does the action do?"""
    leaves_mailbox, irreversible = ACTIONS[kind]
    return Level.ASK if leaves_mailbox or irreversible else Level.SILENT


def email_check(kind: str, flags: Flags) -> Level:
    """Check 2: what does the email contain?"""
    if flags.injection:
        return Level.ESCALATE
    if flags.money:
        if kind == "label":
            return Level.SILENT
        return Level.ASK if is_external(kind) else Level.NOTIFY
    return Level.SILENT


def final_level(kind: str, flags: Flags, learned: Level) -> Level:
    return min(action_check(kind), email_check(kind, flags), learned)
