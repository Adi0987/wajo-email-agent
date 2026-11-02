import unittest

from app.interpreter import Interpreter


class TestInterpreter(unittest.TestCase):
    def setUp(self):
        self.offline = Interpreter(None)

    def test_greeting_is_not_remembered(self):
        self.assertEqual(self.offline.chat("hello there wajo!", "")["remember"], "")

    def test_statement_about_the_user_is_remembered(self):
        self.assertEqual(self.offline.chat("I run the research group", "")["remember"], "I run the research group")

    def test_do_this_instead(self):
        result = self.offline("no, label it research", "question")
        self.assertEqual((result["decision"], result["instead"]["kind"], result["instead"]["label"]),
                         ("no", "label", "research"))
