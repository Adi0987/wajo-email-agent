"""Check 3: approval rates learned from user feedback."""

import math
from collections import defaultdict
from typing import Optional

from policy.models import Level

# Chosen by eval/tune.py: lowest ask rate with at most 5% wrong autonomous actions.
REJECTION_WEIGHT = 1
NOTIFY_AT = 0.60
SILENT_AT = 0.80
KIND_WEIGHT = 10  # the kind of email's record counts as up to 10 responses,
# minus one for each of the sender's own responses
Z = 1.2816  # one-sided 90% confidence


def cautious_rate(approvals: float, rejections: float) -> float:
    """Lower bound of the approval rate (Wilson score). 0 with no responses."""
    n = approvals + rejections
    if n == 0:
        return 0.0
    p = approvals / n
    centre = p + Z * Z / (2 * n)
    margin = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    return (centre - margin) / (1 + Z * Z / n)


class ApprovalRates:
    def __init__(
        self, rejection_weight: float = REJECTION_WEIGHT, notify_at: float = NOTIFY_AT, silent_at: float = SILENT_AT
    ):
        self.rejection_weight = rejection_weight
        self.notify_at = notify_at
        self.silent_at = silent_at
        # (action, sender) and (action, kind of email) -> [approvals, rejections]
        self.by_sender = defaultdict(lambda: [0.0, 0.0])
        self.by_kind = defaultdict(lambda: [0.0, 0.0])

    def record(self, action: str, sender: str, email_kind: str, approved: bool) -> None:
        index, amount = (0, 1) if approved else (1, self.rejection_weight)
        self.by_sender[(action, sender)][index] += amount
        self.by_kind[(action, email_kind)][index] += amount

    def rate(self, action: str, sender: str, email_kind: str) -> float:
        """Cautious approval rate: the sender's own record, plus the kind of email's record while the
        sender has little history of its own. Works from the first email of a new sender."""
        own_a, own_r = self.by_sender[(action, sender)]
        kind_a = self.by_kind[(action, email_kind)][0] - own_a  # excluding this sender's own responses
        kind_r = self.by_kind[(action, email_kind)][1] - own_r
        kind_n = kind_a + kind_r
        weight = max(KIND_WEIGHT - own_a - own_r, 0)
        scale = min(kind_n, weight) / kind_n if kind_n else 0
        return cautious_rate(own_a + kind_a * scale, own_r + kind_r * scale)

    def declined(self, action: str, sender: str, email_kind: str) -> bool:
        """True once the user has mostly said no to this, at least twice (for this sender or kind of email)."""
        for a, r in (self.by_sender[(action, sender)], self.by_kind[(action, email_kind)]):
            if r >= 2 and r > a:
                return True
        return False

    def usual_choice(self, sender: str, email_kind: str) -> Optional[str]:
        """The action the user has approved most for this sender, else for this kind of email."""
        for counts, key in ((self.by_sender, sender), (self.by_kind, email_kind)):
            approvals = {action: a for (action, k), (a, _) in counts.items() if k == key and a > 0}
            if approvals:
                return max(approvals, key=approvals.get)
        return None

    def level(self, action: str, sender: str, email_kind: str) -> Level:
        rate = self.rate(action, sender, email_kind)
        if rate >= self.silent_at:
            return Level.SILENT
        if rate >= self.notify_at:
            return Level.NOTIFY
        return Level.ASK
