"""What the gate has learned, in rows for the Diagnostics tab and the session log."""

from policy.gate import Gate
from policy.rates import cautious_rate

CATEGORY_WORDS = {
    "same_domain": "colleague",
    "contact": "someone you've emailed",
    "newsletter": "newsletter",
    "unknown": "new sender",
}


def learned(gate: Gate) -> dict:
    rates = gate.rates
    senders = [
        {"who": sender, "action": kind.replace("_", " "), "approved": int(a), "rejected": int(r)}
        for (kind, sender), (a, r) in rates.by_sender.items()
        if a or r
    ]
    kinds = [
        {
            "who": group,
            "action": kind.replace("_", " "),
            "approved": int(a),
            "rejected": int(r),
            "rate": f"{cautious_rate(a, r):.0%}",
        }
        for (kind, group), (a, r) in rates.by_kind.items()
        if a or r
    ]
    return {"senders": senders, "groups": kinds}


def timing(gate: Gate) -> list[dict]:
    t = gate.timing
    return [
        {
            "who": CATEGORY_WORDS.get(g, g),
            "follow_up": f"{t.wait[g]:.1f} days",
            "reminder": f"{t.lead[g]:.1f} days before",
        }
        for g in sorted(set(t.wait) | set(t.lead))
    ]
