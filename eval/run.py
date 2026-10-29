"""Runs the eval and writes eval/results_<llm>.md.

    python3 -m eval.run --llm stub        # offline, worst-case stand-in for the LLM
    python3 -m eval.run --llm deepseek    # real LLM, responses cached in eval/llm_cache.json
"""
import argparse
from pathlib import Path

from agent.agent import Agent
from agent.mailbox import Mailbox
from agent.rates import ApprovalRates
from eval import metrics
from eval.baselines import AlwaysAsk, FixedRules
from eval.inbox import USER, build_inbox
from eval.llm_steps import llm_steps
from eval.report import report
from eval.simulate import simulate
from eval.user import SimUser

POLICIES = {"learned": ApprovalRates, "always_ask": AlwaysAsk, "fixed_rules": FixedRules}


def run_once(mode: str, policy: str, seed: int, workers: int) -> dict:
    cases = build_inbox(seed)
    truth = {c.email.id: c for c in cases}
    propose, classify = llm_steps(mode, cases, seed, workers)
    agent = Agent(Mailbox(USER), propose, classify, rates=POLICIES[policy]())
    user = SimUser(cases, seed)
    simulate(cases, agent, user)
    return {
        "learning": metrics.learning(agent, truth),
        "floor": metrics.floor(agent, truth),
        "attacks": metrics.attacks(agent, truth),
        "flags": metrics.flag_recall(agent, truth),
        "deadlines": metrics.deadlines(agent, truth),
        "burden": metrics.burden(agent, truth),
        "timing": user.timing,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", choices=["stub", "deepseek"], default="stub")
    parser.add_argument("--seeds", type=int, nargs="+", default=[101, 102, 103])
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    runs = {policy: [run_once(args.llm, policy, seed, args.workers) for seed in args.seeds] for policy in POLICIES}
    text = report(args.llm, args.seeds, runs)
    Path(f"eval/results_{args.llm}.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
