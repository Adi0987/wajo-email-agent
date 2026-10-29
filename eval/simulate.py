"""Plays an inbox through the agent on a simulated clock."""
from datetime import timedelta

from agent.agent import Agent
from agent.models import Level
from eval.inbox import DAYS, START, Case
from eval.user import SimUser


def simulate(cases: list[Case], agent: Agent, user: SimUser) -> None:
    mail = [(c.email.sent_at, i, c) for i, c in enumerate(cases)]
    ticks = [(START + timedelta(days=d, hours=1), len(cases) + d, None) for d in range(DAYS + 10)]
    notices_seen = log_seen = 0
    for now, _, case in sorted(mail + ticks, key=lambda event: event[:2]):
        if case:
            agent.mailbox.receive(case.email)
            if now < START:
                continue                      # history before the eval starts
            if case.incoming:
                agent.on_new_mail(case.email)
        agent.tick(now)
        while notices_seen < len(agent.notices):
            user.respond(agent, agent.notices[notices_seen], now)
            notices_seen += 1
        while log_seen < len(agent.executor.log):
            entry = agent.executor.log[log_seen]
            log_seen += 1
            if entry["level"] == Level.SILENT and entry["executed"]:
                user.review_silent(agent, entry)
