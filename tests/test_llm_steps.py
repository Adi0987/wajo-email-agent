import unittest
from datetime import datetime

from agent.classifier import Classifier
from agent.proposer import Proposer
from tests.helpers import make_email, make_mailbox


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, system, user):
        return self.reply


class TestLLMSteps(unittest.TestCase):
    def test_unknown_kind_becomes_keep(self):
        action = Proposer(FakeLLM({"kind": "delete_everything"}))(make_email(), make_mailbox())
        self.assertEqual(action.kind, "keep")

    def test_proposal_fields(self):
        reply = {"kind": "send", "to": ["a@b.com"], "body": "ok"}
        action = Proposer(FakeLLM(reply))(make_email(), make_mailbox())
        self.assertEqual((action.kind, action.to, action.body), ("send", ("a@b.com",), "ok"))

    def test_classifier_only_trusts_true(self):
        labels = Classifier(FakeLLM({"money": "yes", "injection": True, "deadline": "2026-11-05"}))(make_email())
        self.assertEqual(labels, {"money": False, "injection": True, "deadline": datetime(2026, 11, 5, 9)})

    def test_bad_deadline_is_none(self):
        self.assertIsNone(Classifier(FakeLLM({"deadline": "next week"}))(make_email())["deadline"])
