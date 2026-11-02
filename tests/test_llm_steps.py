import unittest
from datetime import datetime

from agent.classifier import Classifier
from agent.proposer import Proposer
from tests.helpers import make_email, make_mailbox


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.system = ""

    def complete_json(self, system, user):
        self.system = system
        return self.reply


class TestLLMSteps(unittest.TestCase):
    def test_unknown_kind_becomes_keep(self):
        action = Proposer(FakeLLM({"kind": "delete_everything"}))(make_email(), make_mailbox())
        self.assertEqual(action.kind, "keep")

    def test_proposal_fields(self):
        reply = {"kind": "forward", "to": ["a@b.com"]}
        action = Proposer(FakeLLM(reply))(make_email(), make_mailbox())
        self.assertEqual((action.kind, action.to), ("forward", ("a@b.com",)))

    def test_never_volunteers_a_reply(self):
        for kind in ("draft_reply", "send"):
            action = Proposer(FakeLLM({"kind": kind, "body": "hi"}))(make_email(), make_mailbox())
            self.assertEqual(action.kind, "keep")

    def test_usual_choice_goes_in_prompt(self):
        llm = FakeLLM({"kind": "archive"})
        Proposer(llm)(make_email(), make_mailbox(), usual="archive")
        self.assertIn("usually chooses: archive", llm.system)

    def test_profile_goes_in_prompt(self):
        from agent.profile import Profile
        profile = Profile()
        profile.add("I run the research group")
        llm = FakeLLM({"kind": "archive"})
        Proposer(llm, profile)(make_email(), make_mailbox())
        self.assertIn("- I run the research group", llm.system)

    def test_empty_profile_leaves_prompt_unchanged(self):
        from agent.profile import Profile
        with_profile, without = FakeLLM({"kind": "archive"}), FakeLLM({"kind": "archive"})
        Proposer(with_profile, Profile())(make_email(), make_mailbox())
        Proposer(without)(make_email(), make_mailbox())
        self.assertEqual(with_profile.system, without.system)

    def test_classifier_only_trusts_true(self):
        labels = Classifier(FakeLLM({"money": "yes", "injection": True, "deadline": "2026-11-05"}))(make_email())
        self.assertEqual(labels, {"money": False, "injection": True, "deadline": datetime(2026, 11, 5, 9)})

    def test_bad_deadline_is_none(self):
        self.assertIsNone(Classifier(FakeLLM({"deadline": "next week"}))(make_email())["deadline"])
