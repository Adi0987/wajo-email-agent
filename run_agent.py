"""Try the agent on emails you type. Uses DeepSeek (LLM_API_KEY in .env).

    python3 run_agent.py

At the "From" prompt you can also type:
    wait <days>   move the clock forward (follow-ups and deadline reminders fire)
    quit
Mail "From: me@wajo.ai" is your own sent mail: it isn't processed, but it can get a follow-up nudge.
A subject starting with "Re: " joins the thread with that subject.
"""
from datetime import datetime, timedelta

from agent.agent import Agent
from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.models import Email, Level
from agent.notices import Notice
from agent.proposer import Proposer

USER = "me@wajo.ai"


class Session:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.now = datetime.now().replace(second=0, microsecond=0)
        self.notices_seen = 0
        self.log_seen = 0

    def run(self) -> None:
        print(__doc__)
        while True:
            line = input("\nFrom: ").strip().lower()
            if line == "quit":
                return
            if line.startswith("wait"):
                self.now += timedelta(days=float(line.split()[1]))
                print(f"  Clock is now {self.now:%b %d %H:%M}")
            elif line:
                self.receive(line)
            self.agent.tick(self.now)
            self.show_decisions()
            self.answer_notices()

    def receive(self, sender: str) -> None:
        subject = input("Subject: ").strip()
        print("Body (end with an empty line):")
        body = "\n".join(iter(lambda: input(), ""))
        self.now += timedelta(minutes=1)
        mailbox = self.agent.mailbox
        email_id = f"m{len(mailbox.emails) + 1}"
        thread_id = next((e.thread_id for e in mailbox.emails.values()
                          if subject.lower().startswith("re: ") and e.subject == subject[4:]), email_id)
        recipients = (input("To: ").strip().lower(),) if sender == USER else (USER,)
        email = Email(email_id, thread_id, sender, recipients, subject, body, self.now)
        mailbox.receive(email)
        if sender != USER:
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
    llm = LLM(cache_path=".llm_cache_local.json")   # keeps your emails out of the eval cache
    Session(Agent(Mailbox(USER), Proposer(llm), Classifier(llm))).run()


if __name__ == "__main__":
    main()
