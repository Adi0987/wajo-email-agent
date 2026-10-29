import unittest

from agent.checks import ACTIONS, action_check, email_check
from agent.models import Flags, Level

NO_FLAGS = Flags()


def final_level(kind, flags, learned):
    return min(action_check(kind), email_check(kind, flags), learned)
EXTERNAL = ["send", "forward", "unsubscribe"]
INTERNAL = [kind for kind in ACTIONS if kind not in EXTERNAL]


class TestChecks(unittest.TestCase):
    def test_internal_actions_follow_learning(self):
        for kind in INTERNAL:
            self.assertEqual(final_level(kind, NO_FLAGS, Level.SILENT), Level.SILENT)

    def test_external_actions_never_pass_ask(self):
        for kind in EXTERNAL:
            self.assertEqual(final_level(kind, NO_FLAGS, Level.SILENT), Level.ASK)

    def test_money(self):
        money = Flags(money=True)
        self.assertEqual(final_level("label", money, Level.SILENT), Level.SILENT)
        self.assertEqual(final_level("archive", money, Level.SILENT), Level.NOTIFY)
        self.assertEqual(final_level("send", money, Level.SILENT), Level.ASK)

    def test_injection_escalates_every_action(self):
        for kind in ACTIONS:
            self.assertEqual(final_level(kind, Flags(injection=True), Level.SILENT), Level.ESCALATE)

    def test_learning_can_only_lower(self):
        self.assertEqual(final_level("archive", NO_FLAGS, Level.ASK), Level.ASK)
