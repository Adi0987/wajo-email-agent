"""The conversation layer, offline: the user's own words drive real actions in the mailbox."""
import unittest

from agent.agent import Agent
from agent.audit import AuditLog
from agent.models import Action
from agent.profile import Profile
from app.assistant import Assistant
from tests.helpers import USER, make_email, make_mailbox


def assistant_proposing(kind="archive"):
    agent = Agent(make_mailbox(), lambda email, mailbox, usual=None: Action(kind, email.id),
                  lambda email: {"money": False, "injection": False, "deadline": None})
    return Assistant(agent, None, Profile(), AuditLog())


class TestConversation(unittest.TestCase):
    def setUp(self):
        self.wajo = assistant_proposing("archive")
        self.wajo.deliver(make_email(id="e1", sender="andreas@garp.com", subject="GARP convention", body="Join us"))

    def test_decline_and_reminder(self):
        self.wajo.say("no, do not archive it, remind me tomorrow to deal with it")
        self.assertNotIn("e1", self.wajo.agent.mailbox.archived)
        self.assertEqual([s["what"] for s in self.wajo.scheduled()], ['Remind you about "GARP convention" (you asked)'])

    def test_reply_is_drafted_shown_and_sent_only_after_ok(self):
        self.wajo.say("draft a reply saying I won't be visiting")
        mailbox = self.wajo.agent.mailbox
        self.assertIn("I won't be visiting", mailbox.drafts["e1"])
        self.assertNotIn("e1-reply", mailbox.emails)                      # not sent yet
        question = [m for m in self.wajo.messages if m["open"]][-1]
        self.assertIn("I won't be visiting", question["draft"])
        self.wajo.say("send it")
        self.assertIn("e1-reply", mailbox.emails)

    def test_reply_request_is_not_a_rejection(self):
        self.wajo.say("draft a reply saying thanks")
        self.assertEqual(self.wajo.agent.rates.by_sender[("archive", "andreas@garp.com")], [1, 0])

    def test_sending_is_not_learned_as_a_preference(self):
        self.wajo.say("draft a reply saying thanks")
        self.wajo.say("send it")
        learned = {kind for (kind, _), counts in self.wajo.agent.rates.by_sender.items() if any(counts)}
        self.assertFalse(learned & {"send", "draft_reply"})

    def test_drafting_gives_no_small_talk(self):
        replies = self.wajo.say("draft a reply saying thanks")
        self.assertNotIn("Sample a new email", " ".join(m.get("text", "") for m in replies))

    def test_question_about_the_draft_is_answered_from_the_mailbox(self):
        self.wajo.say("draft a reply saying thanks")
        replies = self.wajo.say("what is the draft?")
        self.assertIn("Thanks", replies[-1]["text"])

    def test_profile_sign_off_used_in_drafts(self):
        self.wajo.profile.add("Always sign emails Best, Adi")
        self.wajo.say("draft a reply saying thanks")
        self.assertTrue(self.wajo.agent.mailbox.drafts["e1"].endswith("Best, Adi"))
