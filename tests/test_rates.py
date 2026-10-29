import unittest

from agent.models import Level
from agent.rates import ApprovalRates


def approve(rates, n, sender="a@news.com", kind="archive"):
    for _ in range(n):
        rates.record(kind, sender, "newsletter", approved=True)


class TestRates(unittest.TestCase):
    def test_starts_at_ask(self):
        self.assertEqual(ApprovalRates().level("archive", "a@news.com", "newsletter"), Level.ASK)

    def test_promotion_thresholds(self):
        rates = ApprovalRates(notify_at=0.60, silent_at=0.85)
        approve(rates, 2)
        self.assertEqual(rates.level("archive", "a@news.com", "newsletter"), Level.ASK)
        approve(rates, 1)
        self.assertEqual(rates.level("archive", "a@news.com", "newsletter"), Level.NOTIFY)
        approve(rates, 7)
        self.assertEqual(rates.level("archive", "a@news.com", "newsletter"), Level.SILENT)

    def test_one_undo_drops_silent_to_notify(self):
        rates = ApprovalRates()
        approve(rates, 15)
        rates.record("archive", "a@news.com", "newsletter", approved=False)
        self.assertEqual(rates.level("archive", "a@news.com", "newsletter"), Level.NOTIFY)

    def test_new_sender_borrows_category(self):
        rates = ApprovalRates()
        approve(rates, 15)
        self.assertEqual(rates.level("archive", "b@news.com", "newsletter"), Level.SILENT)

    def test_no_drop_when_sender_builds_history(self):
        rates = ApprovalRates()
        approve(rates, 15)
        before = rates.rate("archive", "b@news.com", "newsletter")
        approve(rates, 5, sender="b@news.com")
        self.assertGreaterEqual(rates.rate("archive", "b@news.com", "newsletter"), before)

    def test_own_history_replaces_category(self):
        rates = ApprovalRates()
        for _ in range(10):
            rates.record("archive", "a@news.com", "newsletter", approved=False)
        approve(rates, 10, sender="b@news.com")
        self.assertEqual(rates.level("archive", "b@news.com", "newsletter"), Level.SILENT)

    def test_usual_choice(self):
        rates = ApprovalRates()
        self.assertIsNone(rates.usual_choice("a@news.com", "newsletter"))
        approve(rates, 3)
        rates.record("trash", "a@news.com", "newsletter", approved=True)
        self.assertEqual(rates.usual_choice("a@news.com", "newsletter"), "archive")
        self.assertEqual(rates.usual_choice("new@news.com", "newsletter"), "archive")

    def test_actions_learn_separately(self):
        rates = ApprovalRates()
        approve(rates, 15)
        self.assertEqual(rates.level("trash", "a@news.com", "newsletter"), Level.ASK)
