import unittest

from app.interpreter import Interpreter


def turn(text, has_question=True):
    return Interpreter(None).turn(text, "", has_question)


class TestInterpreter(unittest.TestCase):
    def test_greeting_is_not_remembered(self):
        self.assertEqual(turn("hello there wajo!", False)["remember"], "")

    def test_statement_about_the_user_is_remembered(self):
        self.assertEqual(turn("I run the research group", False)["remember"], "I run the research group")

    def test_objection_with_reminder_request(self):
        result = turn("no, do not archive it, remind me tomorrow to deal with it")
        self.assertEqual((result["answer"], result["remind_in_days"]), ("no", 1.0))

    def test_do_this_instead(self):
        result = turn("no, label it research")
        self.assertEqual((result["answer"], result["instead"]["kind"], result["instead"]["label"]),
                         ("no", "label", "research"))

    def test_reply_request(self):
        self.assertEqual(turn("draft a reply saying I won't be visiting")["reply"],
                         {"instructions": "I won't be visiting"})

    def test_send(self):
        self.assertTrue(turn("send it")["send"])
