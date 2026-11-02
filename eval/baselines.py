"""Baselines that replace learning. Checks 1 and 2 still apply."""

from policy.models import Level


class NoLearning:
    """Records nothing, so nothing is ever learned."""

    by_sender: dict = {}
    by_kind: dict = {}

    def record(self, *args, **kwargs) -> None:
        pass

    def rate(self, *args) -> float:
        return 0.0

    def usual_choice(self, sender: str, email_kind: str) -> None:
        return None

    def declined(self, *args) -> bool:
        return False


class AlwaysAsk(NoLearning):
    def level(self, action: str, sender: str, email_kind: str) -> Level:
        return Level.ASK


class FixedRules(NoLearning):
    """Silent for newsletters, Notify for everything else."""

    def level(self, action: str, sender: str, email_kind: str) -> Level:
        return Level.SILENT if email_kind == "newsletter" else Level.NOTIFY
