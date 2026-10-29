"""Baselines that replace learning. Checks 1 and 2 still apply."""
from agent.models import Level


class AlwaysAsk:
    def record(self, *args, **kwargs) -> None:
        pass

    def usual_choice(self, sender: str, category: str) -> None:
        return None

    def level(self, kind: str, sender: str, category: str) -> Level:
        return Level.ASK


class FixedRules:
    """Silent for newsletters, Notify for everything else. Never learns."""
    def record(self, *args, **kwargs) -> None:
        pass

    def usual_choice(self, sender: str, category: str) -> None:
        return None

    def level(self, kind: str, sender: str, category: str) -> Level:
        return Level.SILENT if category == "newsletter" else Level.NOTIFY
