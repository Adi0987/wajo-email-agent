"""Picks rate settings on tuning seeds, separate from the reported seeds.
Called by `python3 wajo.py tune`.

Rule: the lowest ask rate whose wrong-autonomous-action rate is at most MAX_ERROR,
measured on the second half of each run (after the cold start).
"""
import itertools

from agent.agent import Agent
from agent.mailbox import Mailbox
from agent.rates import ApprovalRates
from eval import metrics
from eval.inbox import USER, build_inbox
from eval.llm_steps import llm_steps
from eval.simulate import simulate
from eval.user import SimUser

MAX_ERROR = 0.05
TUNING_SEEDS = [1, 2, 3]
GRID = {"rejection_weight": [1, 2, 3], "notify_at": [0.6, 0.7, 0.8], "silent_at": [0.8, 0.85, 0.9]}


def score(mode: str, settings: dict) -> tuple[float, float]:
    """(ask rate, error rate) over the second half of each tuning run."""
    asks = decisions = errors = autonomous = 0
    for seed in TUNING_SEEDS:
        cases = build_inbox(seed)
        truth = {c.email.id: c for c in cases}
        propose, classify = llm_steps(mode, cases, seed)
        agent = Agent(Mailbox(USER), propose, classify, rates=ApprovalRates(**settings))
        simulate(cases, agent, SimUser(cases, seed))
        rows = metrics.learning(agent, truth)
        for row in rows[len(rows) // 2:]:
            asks += row["asks"]
            decisions += row["decisions"]
            errors += row["errors"]
            autonomous += row["autonomous"]
    return asks / decisions, errors / autonomous if autonomous else 0.0


def tune(mode: str) -> str:
    """Scores every setting in GRID and returns a table plus the chosen setting."""
    results = []
    for values in itertools.product(*GRID.values()):
        settings = dict(zip(GRID, values))
        if settings["silent_at"] > settings["notify_at"]:
            results.append((settings, *score(mode, settings)))
    lines = ["| Rejection weight | Notify at | Silent at | Ask rate | Error rate |", "|---|---|---|---|---|"]
    for settings, ask, error in sorted(results, key=lambda r: r[1]):
        lines.append(f"| {settings['rejection_weight']} | {settings['notify_at']:.0%} | {settings['silent_at']:.0%} "
                     f"| {ask:.0%} | {error:.1%} |")
    best = min((r for r in results if r[2] <= MAX_ERROR), key=lambda r: r[1])
    lines.append(f"\nChosen (error <= {MAX_ERROR:.0%}): {best[0]}. Set these in agent/rates.py.")
    return "\n".join(lines)
