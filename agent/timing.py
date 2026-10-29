"""Learned timing per sender category.

N: days without a reply before a follow-up nudge.
L: days before a deadline to remind the user.
"""
from collections import defaultdict

STEP = 1.5
START_N = 3.0
START_L = 1.0


class Timing:
    def __init__(self):
        self.n = defaultdict(lambda: START_N)
        self.l = defaultdict(lambda: START_L)

    def nudge_feedback(self, category: str, verdict: str) -> None:
        """verdict: "too_early" waits longer next time, "too_late" waits less."""
        if verdict == "too_early":
            self.n[category] *= STEP
        elif verdict == "too_late":
            self.n[category] /= STEP

    def reminder_feedback(self, category: str, verdict: str) -> None:
        """verdict: "too_early" reminds closer to the deadline, "too_late" earlier."""
        if verdict == "too_early":
            self.l[category] /= STEP
        elif verdict == "too_late":
            self.l[category] *= STEP
