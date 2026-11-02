"""Plays an inbox through Wajo on a simulated clock. The simulated user answers the gate's notices."""

from datetime import timedelta

from agent.wajo import Wajo
from eval.inbox import DAYS, START, Case
from eval.user import SimUser
from mailsim.server import MailServer
from policy.models import Level


def simulate(cases: list[Case], wajo: Wajo, user: SimUser, server: MailServer) -> None:
    gate = wajo.gate
    mail = [(c.email.sent_at, i, c) for i, c in enumerate(cases)]
    ticks = [(START + timedelta(days=d, hours=1), len(cases) + d, None) for d in range(DAYS + 10)]
    notices_seen = log_seen = 0
    for now, _, case in sorted(mail + ticks, key=lambda event: event[:2]):
        server.now = now
        if case:
            server.deliver(case.email)
            if now < START:
                continue  # history before the eval starts
            if case.incoming:
                wajo.on_email(case.email, now)
        gate.tick(now)
        while notices_seen < len(gate.notices):
            user.respond(gate, gate.notices[notices_seen], now)
            notices_seen += 1
        while log_seen < len(gate.executor.log):
            entry = gate.executor.log[log_seen]
            log_seen += 1
            if entry["level"] == Level.SILENT and entry["executed"]:
                user.review_silent(gate, entry)
