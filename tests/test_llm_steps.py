"""The LLM brain and classifier: what goes into their prompts and how replies are checked."""

import io
import unittest
import unittest.mock
import urllib.error
from datetime import datetime

from agent.brain import LLMBrain
from agent.classifier import Classifier
from agent.llm import LLM, parse_json
from agent.wajo import Wajo
from policy.gate import Gate
from tests.helpers import T0, make_email, make_mailbox, server_of


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.system = ""

    def complete_json(self, system, user):
        self.system = system
        return self.reply


def wajo_with(reply):
    llm = FakeLLM(reply)
    return Wajo(Gate(make_mailbox()), LLMBrain(llm), lambda e: {"kind": "request"}, talk=False), llm


def arrive(wajo, email=None):
    email = email or make_email()
    server_of(wajo.mail).deliver(email)
    wajo.on_email(email, T0)


class TestLLMClient(unittest.TestCase):
    def test_reads_json_with_or_without_fences(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json('Sure: {"a": 1}'), {"a": 1})

    def test_falls_back_to_a_plain_request_when_json_mode_is_rejected(self):
        llm = LLM(cache_path=None)
        llm.config = {"key": "k", "base_url": "https://example.invalid", "model": "m"}
        bodies = []

        def post(body):
            bodies.append(body)
            if "response_format" in body:
                raise urllib.error.HTTPError("u", 400, "bad request", {}, io.BytesIO(b"json_object not supported"))
            return '{"ok": true}'

        llm._post = post
        self.assertEqual(llm.complete_json("system", "user"), {"ok": True})
        self.assertEqual(["response_format" in b for b in bodies], [True, False])
        self.assertEqual(
            [("max_tokens" in b, "max_completion_tokens" in b) for b in bodies], [(True, False), (False, True)]
        )

    def test_retries_a_dropped_connection(self):
        llm = LLM(cache_path=None)
        llm.config = {"key": "k", "base_url": "https://example.invalid", "model": "m"}
        calls = []

        def post_once(body):
            calls.append(body)
            if len(calls) == 1:
                raise ConnectionResetError(54, "Connection reset by peer")
            return '{"ok": true}'

        llm._post_once = post_once
        with unittest.mock.patch("time.sleep"):
            self.assertEqual(llm.complete_json("system", "user"), {"ok": True})
        self.assertEqual(len(calls), 2)


class TestLLMSteps(unittest.TestCase):
    def test_unknown_kind_becomes_keep(self):
        wajo, _ = wajo_with({"kind": "delete_everything"})
        arrive(wajo)
        self.assertEqual(wajo.gate.executor.log[-1]["action"].kind, "keep")

    def test_proposal_fields(self):
        wajo, _ = wajo_with({"kind": "forward", "to": ["a@b.com"]})
        arrive(wajo)
        action = wajo.gate.executor.log[-1]["action"]
        self.assertEqual((action.kind, action.to), ("forward", ("a@b.com",)))

    def test_context_has_the_email_and_its_kind(self):
        wajo, llm = wajo_with({"kind": "archive"})
        arrive(wajo, make_email(subject="Budget review", body="Can you check the numbers?"))
        self.assertIn("Can you check the numbers?", llm.system)
        self.assertIn("kind: request", llm.system)

    def test_profile_goes_in_context(self):
        wajo, llm = wajo_with({"kind": "archive"})
        wajo.profile.add("I run the research group")
        arrive(wajo)
        self.assertIn("- I run the research group", llm.system)

    def test_feedback_goes_in_context(self):
        wajo, llm = wajo_with({"kind": "archive"})
        arrive(wajo, make_email(id="e1"))
        wajo.gate.reject(wajo.gate.notices[-1], chosen="label")
        arrive(wajo, make_email(id="e2"))
        self.assertIn("I proposed archive; the user said no and chose label", llm.system)
        self.assertIn("archive: from this sender 0 yes / 1 no", llm.system)

    def test_classifier_only_trusts_true(self):
        labels = Classifier(FakeLLM({"money": "yes", "injection": True, "deadline": "2026-11-05"}))(make_email())
        self.assertEqual(
            labels, {"money": False, "injection": True, "deadline": datetime(2026, 11, 5, 9), "kind": "other"}
        )

    def test_bad_deadline_is_none(self):
        self.assertIsNone(Classifier(FakeLLM({"deadline": "next week"}))(make_email())["deadline"])
