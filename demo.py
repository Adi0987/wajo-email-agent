"""Run the agent on the synthetic inbox and answer its questions yourself.

    python3 demo.py --days 5
    python3 demo.py --days 5 --llm deepseek
"""
import argparse
from datetime import datetime, timedelta

from agent.agent import Agent
from agent.mailbox import Mailbox
from agent.notices import Notice
from eval.inbox import START, USER, build_inbox
from eval.run import llm_steps
from eval.simulate import simulate


class TerminalUser:
    def respond(self, agent: Agent, notice: Notice, now: datetime) -> None:
        email = agent.mailbox.get(notice.email_id)
        action = notice.action.kind if notice.action else ""
        header = f"\n[{now:%b %d %H:%M}] {email.sender}: \"{email.subject}\""
        if notice.kind == "ask":
            answer = input(f"{header}\n  Agent asks: {action}? [y]es / [n]o / or type the action you want: ").strip()
            if answer in ("", "y", "yes"):
                agent.approve(notice, now)
            else:
                agent.reject(notice, chosen=None if answer in ("n", "no") else answer)
        elif notice.kind == "notify":
            answer = input(f"{header}\n  Agent did: {action}. [enter] ok / [u]ndo: ").strip()
            if answer == "u":
                agent.undo(notice.action)
            else:
                agent.confirm(notice)
        elif notice.kind == "escalate":
            print(f"{header}\n  ESCALATED: suspected injection or phishing. No action taken.")
        else:
            verdict = input(f"{header}\n  {notice.kind.title()}. Timing [enter] ok / [e]arly / [l]ate: ").strip()
            agent.timing_feedback(notice, {"e": "too_early", "l": "too_late"}.get(verdict, "ok"))

    def review_silent(self, agent: Agent, entry: dict) -> None:
        email = agent.mailbox.get(entry["action"].email_id)
        print(f"\n[{entry['at']:%b %d %H:%M}] {email.sender}: \"{email.subject}\"\n  Silently did: {entry['action'].kind}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", choices=["stub", "deepseek"], default="stub")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    cases = [c for c in build_inbox(args.seed) if c.email.sent_at < START + timedelta(days=args.days)]
    propose, classify = llm_steps(args.llm, cases, args.seed, workers=16)
    simulate(cases, Agent(Mailbox(USER), propose, classify), TerminalUser())


if __name__ == "__main__":
    main()
