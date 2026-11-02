import unittest

from policy.senders import sender_category
from tests.helpers import USER, make_email, make_mailbox


class TestSenders(unittest.TestCase):
    def setUp(self):
        sent = make_email(id="s1", sender=USER, to=("friend@gmail.com",))
        self.mailbox = make_mailbox(sent)

    def category(self, **kwargs):
        return sender_category(make_email(**kwargs), self.mailbox)

    def test_contact(self):
        self.assertEqual(self.category(sender="friend@gmail.com"), "contact")

    def test_same_domain(self):
        self.assertEqual(self.category(sender="boss@example.com"), "same_domain")

    def test_newsletter(self):
        self.assertEqual(self.category(sender="news@shop.com", has_unsubscribe=True), "newsletter")

    def test_spoofed_contact_is_unknown(self):
        self.assertEqual(self.category(sender="friend@gmail.com", authenticated=False), "unknown")

    def test_lookalike_domains_are_unknown(self):
        self.assertEqual(self.category(sender="boss@examp1e.com"), "unknown")
        self.assertEqual(self.category(sender="boss@exаmple.com"), "unknown")  # Cyrillic а
