import unittest

from app.interpreter import Interpreter


class TestInterpreter(unittest.TestCase):
    def setUp(self):
        self.offline = Interpreter(None)

    def test_greeting_is_not_remembered(self):
        self.assertEqual(self.offline.chat("hello there wajo!", "")["remember"], "")

    def test_statement_about_the_user_is_remembered(self):
        self.assertEqual(self.offline.chat("I run the research group", "")["remember"], "I run the research group")

    def test_objection_with_reminder_request(self):
        result = self.offline("why are you drafting such a long email? set me a reminder for 1-day to respond", "q")
        self.assertEqual((result["decision"], result["instead"], result["remind_in_days"]), ("no", None, 1.0))

    def test_do_this_instead(self):
        result = self.offline("no, label it research", "question")
        self.assertEqual((result["decision"], result["instead"]["kind"], result["instead"]["label"]),
                         ("no", "label", "research"))
