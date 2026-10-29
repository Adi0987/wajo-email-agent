"""Pending approval requests. An approval covers one exact action."""
import itertools

from agent.models import Action


class Approvals:
    def __init__(self):
        self.pending: dict[str, Action] = {}
        self.approved: dict[str, Action] = {}
        self._ids = itertools.count(1)

    def request(self, action: Action) -> str:
        approval_id = f"a{next(self._ids)}"
        self.pending[approval_id] = action
        return approval_id

    def approve(self, approval_id: str) -> Action:
        action = self.pending.pop(approval_id)
        self.approved[approval_id] = action
        return action

    def reject(self, approval_id: str) -> Action:
        return self.pending.pop(approval_id)

    def matches(self, approval_id: str, action: Action) -> bool:
        """True only if this exact action was approved."""
        return self.approved.get(approval_id) == action
