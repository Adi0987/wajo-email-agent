"""Try the agent on emails you type, or on a real inbox from the Enron dataset.
Uses DeepSeek (LLM_API_KEY in .env).

    python3 run_agent.py
    python3 run_agent.py --enron maildir --person kaminski-v --count 30

At the "From" prompt you can also type:
    wait <days>   move the clock forward (follow-ups and deadline reminders fire)
    quit
Mail "From: me@wajo.ai" is your own sent mail: it isn't processed, but it can get a follow-up nudge.
A subject starting with "Re: " joins the thread with that subject.
"""
import argparse
from datetime import datetime, timedelta

from agent.agent import Agent
from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Email, Level
from agent.notices import Notice
from agent.proposer import Proposer
from eval import enron

USER = "me@wajo.ai"


class Session:
    def __init__(self, agent: Agent, user: str, feed: list[Email] = ()):
        self.agent = agent
        self.user = user
        self.feed = list(feed)    # emails to deliver one by one; empty means you type them
        self.now = feed[0].sent_at if feed else datetime.now().replace(second=0, microsecond=0)
        self.notices_seen = 0
        self.log_seen = 0

    def run(self) -> None:
        print(__doc__)
        replay = bool(self.feed)
        while True:
            if replay and not self.feed:
                print("\nNo more emails.")
                return
            line = input(f"\n[enter] next email ({len(self.feed)} left), wait <days>, quit: " if replay
                         else "\nFrom: ").strip().lower()
            if line == "quit":
                return
            if line.startswith("wait"):
                self.now += timedelta(days=float(line.split()[1]))
                print(f"  Clock is now {self.now:%b %d %H:%M}")
            elif replay:
                self.deliver(self.feed.pop(0))
            elif line:
                self.receive(line)
            self.agent.tick(self.now)
            self.show_decisions()
            self.answer_notices()

    def deliver(self, email: Email) -> None:
        self.now = max(self.now, email.sent_at)
        preview = " ".join(email.body.split())[:300]
        print(f"\n  [{email.sent_at:%Y-%m-%d %H:%M}] From {email.sender}\n  Subject: {email.subject}\n  {preview}")
        self.agent.mailbox.receive(email)
        self.agent.on_new_mail(email)

    def receive(self, sender: str) -> None:
        subject = input("Subject: ").strip()
        print("Body (end with an empty line):")
        body = "\n".join(iter(lambda: input(), ""))
        self.now += timedelta(minutes=1)
        mailbox = self.agent.mailbox
        email_id = f"m{len(mailbox.emails) + 1}"
        thread_id = next((e.thread_id for e in mailbox.emails.values()
                          if subject.lower().startswith("re: ") and e.subject == subject[4:]), email_id)
        recipients = (input("To: ").strip().lower(),) if sender == self.user else (self.user,)
        email = Email(email_id, thread_id, sender, recipients, subject, body, self.now)
        mailbox.receive(email)
        if sender != self.user:
            self.agent.on_new_mail(email)

    def show_decisions(self) -> None:
        for entry in self.agent.executor.log[self.log_seen:]:
            if not entry["approved"]:
                checks, action = entry["checks"], entry["action"]
                target = f" to {', '.join(action.to)}" if action.to else ""
                labels = self.agent.labels.get(action.email_id, {})
                flags = [name for name in ("money", "injection") if labels.get(name)]
                print(f"  Agent proposes: {action.kind}{target}"
                      + (f"   (classifier: {', '.join(flags)})" if flags else ""))
                print(f"  Checks: action {checks['action'].name} · email {checks['email'].name} · "
                      f"learned {checks['learned'].name} → {entry['level'].name}")
                if entry["level"] == Level.SILENT:
                    print(f"  Done silently: {action.kind}")
        self.log_seen = len(self.agent.executor.log)

    def answer_notices(self) -> None:
        while self.notices_seen < len(self.agent.notices):
            notice = self.agent.notices[self.notices_seen]
            self.notices_seen += 1
            self.answer(notice)

    def answer(self, notice: Notice) -> None:
        agent = self.agent
        subject = agent.mailbox.get(notice.email_id).subject
        if notice.kind == "ask":
            answer = input(f"  ASK: {notice.action.kind}? [y]es / [n]o / or type the action you want: ").strip()
            if answer in ("", "y", "yes"):
                agent.approve(notice, self.now)
            else:
                agent.reject(notice, chosen=None if answer in ("n", "no") else answer)
        elif notice.kind == "notify":
            if input(f"  NOTIFY: did {notice.action.kind}. [enter] ok / [u]ndo: ").strip() == "u":
                agent.undo(notice.action)
            else:
                agent.confirm(notice)
        elif notice.kind == "escalate":
            print("  ESCALATE: suspected injection or phishing. No action taken.")
        else:
            verdict = input(f"  {notice.kind.upper()} for \"{subject}\". Timing [enter] ok / [e]arly / [l]ate: ").strip()
            agent.timing_feedback(notice, {"e": "too_early", "l": "too_late"}.get(verdict, "ok"))
        self.show_decisions()   # an approval runs the action


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enron", help="path to the Enron maildir folder")
    parser.add_argument("--person", default="kaminski-v", help="whose inbox to use, e.g. kaminski-v")
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args()
    user, history, feed = USER, [], []
    if args.enron:
        user, history, feed = enron.load(args.enron, args.person, args.count)
        print(f"Acting as {user}: {len(history)} sent emails loaded as history, {len(feed)} inbox emails to go.")
    mailbox = Mailbox(user)
    for email in history:             # past sent mail: makes contacts, never processed
        mailbox.receive(email)
    llm = LLM(cache_path=".llm_cache_local.json")   # keeps these emails out of the eval cache
    Session(Agent(mailbox, Proposer(llm), Classifier(llm)), user, feed).run()


if __name__ == "__main__":
    main()
