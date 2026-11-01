"""Try the agent on emails you type, or on a real inbox from the Enron dataset.
Uses DeepSeek (LLM_API_KEY in .env).

    python3 run_agent.py
    python3 run_agent.py --enron enron-email-dataset.zip --person kaminski-v --count 30

At the "From" prompt you can also type:
    wait <days>   move the clock forward (follow-ups and deadline reminders fire)
    quit
Mail "From: me@wajo.ai" is your own sent mail: it isn't processed, but it can get a follow-up nudge.
A subject starting with "Re: " joins the thread with that subject.
"""
import argparse
from datetime import datetime, timedelta

from agent.agent import Agent
from agent.audit import AuditLog
from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Email, Level
from agent.notices import Notice
from agent.proposer import Proposer
from agent.senders import other_party
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
        self.audit = AuditLog(f"runs/audit_{datetime.now():%Y%m%d_%H%M%S}.csv")

    def run(self) -> None:
        print(__doc__)
        replay = bool(self.feed)
        while True:
            if replay and not self.feed:
                print("\nNo more emails.")
                break
            line = input(f"\n[enter] next email ({len(self.feed)} left), wait <days>, quit: " if replay
                         else "\nFrom: ").strip().lower()
            if line == "quit":
                break
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
        print("\n" + self.audit.summary())

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
                email = self.agent.mailbox.get(action.email_id)
                self.audit.decision(entry, email, other_party(email, self.agent.mailbox)[1], labels)
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
                response = "approved"
            else:
                chosen = None if answer in ("n", "no") else answer
                agent.reject(notice, chosen=chosen)
                response = f"rejected, wanted {chosen}" if chosen else "rejected"
        elif notice.kind == "notify":
            if input(f"  NOTIFY: did {notice.action.kind}. [enter] ok / [u]ndo: ").strip() == "u":
                agent.undo(notice.action)
                response = "undone"
            else:
                agent.confirm(notice)
                response = "confirmed"
        elif notice.kind == "escalate":
            print("  ESCALATE: suspected injection or phishing. No action taken.")
            response = "escalated"
        else:
            answer = input(f"  {notice.kind.upper()} for \"{subject}\". Timing [enter] ok / [e]arly / [l]ate: ").strip()
            verdict = {"e": "too_early", "l": "too_late"}.get(answer, "ok")
            agent.timing_feedback(notice, verdict)
            response = f"{notice.kind} timing {verdict.replace('_', ' ')}"
        self.audit.response(notice.email_id, response)
        self.show_decisions()   # an approval runs the action


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enron", help="Enron dataset: the Kaggle zip or the CMU maildir folder")
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
