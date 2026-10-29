"""Checks 1 and 2: the safety floor. Fixed rules, no learned state.

Check 3 (learned) is in agent.rates. The executor takes the most cautious of the three.
"""
from agent.models import Flags, Level

# action: (leaves the mailbox, can't be undone)
ACTIONS = {
    "keep":        (False, False),   # leave it in the inbox
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

