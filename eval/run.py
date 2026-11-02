"""Runs the eval and writes eval/results_<llm>.md. Called by `python3 wajo.py eval`."""

from pathlib import Path

from agent.wajo import Wajo
from eval import metrics
from eval.baselines import AlwaysAsk, FixedRules
from eval.inbox import USER, build_inbox
from eval.llm_steps import llm_steps
from eval.report import report
from eval.simulate import simulate
from eval.user import SimUser
from mailsim.server import connect
from policy.gate import Gate
from policy.rates import ApprovalRates

POLICIES = {"learned": ApprovalRates, "always_ask": AlwaysAsk, "fixed_rules": FixedRules}
REPORT_SEEDS = [101, 102, 103]


def run_once(mode: str, policy: str, seed: int) -> dict:
    cases = build_inbox(seed)
    truth = {c.email.id: c for c in cases}
    brain, classify = llm_steps(mode, cases, seed)
    server, mail = connect(USER)
    gate = Gate(mail, rates=POLICIES[policy]())
    user = SimUser(cases, seed)
    simulate(cases, Wajo(gate, brain, classify, talk=False), user, server)
    return {
        "learning": metrics.learning(gate, truth),
        "floor": metrics.floor(gate, truth),
        "attacks": metrics.attacks(gate, truth),
        "flags": metrics.flag_recall(gate, truth),
        "deadlines": metrics.deadlines(gate, truth),
        "burden": metrics.burden(gate, truth),
        "timing": user.timing,
    }


def run_eval(mode: str) -> str:
    """Runs every policy on the report seeds, writes the results file, returns its text."""
    runs = {policy: [run_once(mode, policy, seed) for seed in REPORT_SEEDS] for policy in POLICIES}
    text = report(mode, REPORT_SEEDS, runs)
    Path(f"eval/results_{mode}.md").write_text(text)
    return text
