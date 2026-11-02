"""Pending approval requests. An approval covers one exact action."""

import itertools

from policy.models import Action


class Approvals:
    def __init__(self):
        self.pending: dict[str, Action] = {}
        self.approved: dict[str, Action] = {}
        self._ids = itertools.count(1)

    def request(self, action: Action) -> str:
        approval_id = f"a{next(self._ids)}"
        self.pending[approval_id] = action
        return approval_id

    def approve(self, approval_id: str) -> None:
        self.approved[approval_id] = self.pending.pop(approval_id)

    def reject(self, approval_id: str) -> None:
        self.pending.pop(approval_id)

    def use(self, approval_id: str, action: Action) -> bool:
        """True only if this exact action was approved. Each approval works once."""
        return self.approved.pop(approval_id, None) == action
