"""Check 3: approval rates learned from user feedback."""
import math
from collections import defaultdict
from typing import Optional

from agent.models import Level

# Chosen by eval/tune.py: lowest ask rate with at most 5% wrong autonomous actions.
REJECTION_WEIGHT = 1
NOTIFY_AT = 0.60
SILENT_AT = 0.80
CATEGORY_WEIGHT = 10      # once a sender has a response of its own, its category counts as up to
                          # 10 responses, minus one for each of the sender's own responses
Z = 1.2816                # one-sided 90% confidence


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
    def __init__(self, rejection_weight: float = REJECTION_WEIGHT,
                 notify_at: float = NOTIFY_AT, silent_at: float = SILENT_AT):
        self.rejection_weight = rejection_weight
        self.notify_at = notify_at
        self.silent_at = silent_at
        # (action, sender) and (action, category) -> [approvals, rejections]
        self.by_sender = defaultdict(lambda: [0.0, 0.0])
        self.by_category = defaultdict(lambda: [0.0, 0.0])

    def record(self, kind: str, sender: str, category: str, approved: bool) -> None:
        index, amount = (0, 1) if approved else (1, self.rejection_weight)
        self.by_sender[(kind, sender)][index] += amount
        self.by_category[(kind, category)][index] += amount

    def rate(self, kind: str, sender: str, category: str) -> float:
        own_a, own_r = self.by_sender[(kind, sender)]
        # category history, excluding this sender's own responses
        cat_a = self.by_category[(kind, category)][0] - own_a
        cat_r = self.by_category[(kind, category)][1] - own_r
        cat_n = cat_a + cat_r
        own_n = own_a + own_r
        weight = max(CATEGORY_WEIGHT - own_n, 0) if own_n else 0   # a sender's first email always asks
        scale = min(cat_n, weight) / cat_n if cat_n else 0
        return cautious_rate(own_a + cat_a * scale, own_r + cat_r * scale)

    def usual_choice(self, sender: str, category: str) -> Optional[str]:
        """The action the user has approved most for this sender, else for its category."""
        for counts, key in ((self.by_sender, sender), (self.by_category, category)):
            approvals = {kind: a for (kind, k), (a, _) in counts.items() if k == key and a > 0}
            if approvals:
                return max(approvals, key=approvals.get)
        return None

    def level(self, kind: str, sender: str, category: str) -> Level:
        rate = self.rate(kind, sender, category)
        if rate >= self.silent_at:
            return Level.SILENT
        if rate >= self.notify_at:
            return Level.NOTIFY
        return Level.ASK
