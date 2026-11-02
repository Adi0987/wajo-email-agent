"""Runs the eval and writes eval/results_<llm>.md. Called by `python3 wajo.py eval`."""
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
REPORT_SEEDS = [101, 102, 103]


def run_once(mode: str, policy: str, seed: int) -> dict:
    cases = build_inbox(seed)
    truth = {c.email.id: c for c in cases}
    propose, classify = llm_steps(mode, cases, seed)
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


def run_eval(mode: str) -> str:
    """Runs every policy on the report seeds, writes the results file, returns its text."""
    runs = {policy: [run_once(mode, policy, seed) for seed in REPORT_SEEDS] for policy in POLICIES}
    text = report(mode, REPORT_SEEDS, runs)
    Path(f"eval/results_{mode}.md").write_text(text)
    return text
