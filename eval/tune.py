"""Picks rate settings on tuning seeds, separate from the reported seeds.

Rule: the lowest ask rate whose wrong-autonomous-action rate is at most MAX_ERROR,
measured on the second half of each run (after the cold start).

    python3 -m eval.tune --llm stub
"""
import argparse
import itertools

from agent.agent import Agent
from agent.mailbox import Mailbox
from agent.rates import ApprovalRates
from eval import metrics
from eval.inbox import USER, build_inbox
from eval.run import llm_steps
from eval.simulate import simulate
from eval.user import SimUser

MAX_ERROR = 0.05
TUNING_SEEDS = [1, 2, 3]
GRID = {"rejection_weight": [1, 2, 3], "notify_at": [0.6, 0.7, 0.8], "silent_at": [0.8, 0.85, 0.9]}


def score(mode: str, settings: dict, workers: int) -> tuple[float, float]:
    """(ask rate, error rate) over the second half of each tuning run."""
    asks = decisions = errors = autonomous = 0
    for seed in TUNING_SEEDS:
        cases = build_inbox(seed)
        truth = {c.email.id: c for c in cases}
        propose, classify = llm_steps(mode, cases, seed, workers)
        agent = Agent(Mailbox(USER), propose, classify, rates=ApprovalRates(**settings))
        simulate(cases, agent, SimUser(cases, seed))
        rows = metrics.learning(agent, truth)
        for row in rows[len(rows) // 2:]:
            asks += row["asks"]
            decisions += row["decisions"]
            errors += row["errors"]
            autonomous += row["autonomous"]
    return asks / decisions, errors / autonomous if autonomous else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", choices=["stub", "deepseek"], default="stub")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    results = []
    for values in itertools.product(*GRID.values()):
        settings = dict(zip(GRID, values))
        if settings["silent_at"] > settings["notify_at"]:
            results.append((settings, *score(args.llm, settings, args.workers)))
    print("| Rejection weight | Notify at | Silent at | Ask rate | Error rate |\n|---|---|---|---|---|")
    for settings, ask, error in sorted(results, key=lambda r: r[1]):
        print(f"| {settings['rejection_weight']} | {settings['notify_at']:.0%} | {settings['silent_at']:.0%} "
              f"| {ask:.0%} | {error:.1%} |")
    within = [r for r in results if r[2] <= MAX_ERROR]
    best = min(within, key=lambda r: r[1])
    print(f"\nChosen (error <= {MAX_ERROR:.0%}): {best[0]}")


if __name__ == "__main__":
    main()
