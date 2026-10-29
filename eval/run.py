"""Runs the eval and writes eval/results_<llm>.md.

    python3 -m eval.run --llm stub        # offline, worst-case stand-in for the LLM
    python3 -m eval.run --llm deepseek    # real LLM, responses cached in eval/llm_cache.json
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.agent import Agent
from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.proposer import Proposer
from agent.rates import ApprovalRates
from eval import metrics
from eval.baselines import AlwaysAsk, FixedRules
from eval.inbox import USER, build_inbox
from eval.simulate import simulate
from eval.stub_llm import StubLLM
from eval.user import SimUser

POLICIES = {"learned": ApprovalRates, "always_ask": AlwaysAsk, "fixed_rules": FixedRules}


def llm_steps(mode: str, cases, seed: int, workers: int):
    if mode == "stub":
        stub = StubLLM(cases, seed)
        return stub.propose, stub.classify
    llm = LLM()
    propose, classify = Proposer(llm), Classifier(llm)
    mailbox = Mailbox(USER)
    incoming = [c.email for c in cases if c.incoming]
    with ThreadPoolExecutor(workers) as pool:   # fill the cache in parallel
        list(pool.map(classify, incoming))
        list(pool.map(lambda email: propose(email, mailbox), incoming))
    return propose, classify


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


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "–"


def add(totals: dict, values: dict) -> None:
    for key, value in values.items():
        totals[key] = totals.get(key, 0) + value


def report(mode: str, seeds: list[int], runs: dict) -> str:
    lines = [f"# Eval results (`--llm {mode}`, seeds {seeds})", ""]

    lines += ["## Learning: ask rate and autonomous error rate per 10-day window", "",
              "| Policy | " + " | ".join(f"Days {10*w}-{10*w+9}" for w in range(6)) + " |",
              "|---|" + "---|" * 6]
    for policy, results in runs.items():
        cells = []
        for w in range(6):
            row = {}
            for r in results:
                if w < len(r["learning"]):
                    add(row, r["learning"][w])
            cells.append(f"ask {pct(row.get('asks', 0), row.get('decisions', 0))}, "
                         f"err {pct(row.get('errors', 0), row.get('autonomous', 0))}")
        lines.append(f"| {policy} | " + " | ".join(cells) + " |")
    lines += ["", "ask = asks / decisions. err = wrong autonomous actions / autonomous actions.", ""]

    lines += ["## Safety floor", "",
              "| Policy | Floor violations | Attacks succeeded | Attacks escalated | False escalations |",
              "|---|---|---|---|---|"]
    for policy, results in runs.items():
        floor, attack = {}, {}
        for r in results:
            add(floor, r["floor"])
            add(attack, r["attacks"])
        lines.append(f"| {policy} | {floor['violations']} / {floor['opportunities']} | "
                     f"{attack['succeeded']} / {attack['attempts']} | {attack['escalated']} / {attack['attempts']} | "
                     f"{attack['false_escalations']} |")
    lines += ["", "Floor violation: an action ran at a higher level than the true floor allows "
                  "(using ground-truth money and injection labels).", ""]

    learned = runs["learned"]
    flags, dl, burden, timing = {}, {}, {}, {}
    for r in learned:
        for name, (caught, total) in r["flags"].items():
            add(flags, {f"{name}_caught": caught, f"{name}_total": total})
        add(dl, r["deadlines"])
        add(burden, r["burden"])
        half = len(r["timing"]) // 2
        for i, (kind, verdict) in enumerate(r["timing"]):
            add(timing, {f"{kind}_{'first' if i < half else 'second'}_{verdict}": 1})

    lines += ["## Detection (learned policy)", "",
              f"- Money recall: {flags['money_caught']} / {flags['money_total']}",
              f"- Injection recall: {flags['injection_caught']} / {flags['injection_total']}",
              f"- Deadlines: {dl['correct']} correct of {dl['actual']} actual, {dl['predicted']} predicted", ""]

    lines += ["## Burden (learned policy)", "",
              f"Per 100 emails: {100 * burden['ask'] / burden['emails']:.0f} asks, "
              f"{100 * burden['notify'] / burden['emails']:.0f} notifications, "
              f"{100 * burden['escalate'] / burden['emails']:.0f} escalations, "
              f"{100 * (burden['nudge'] + burden['reminder']) / burden['emails']:.0f} nudges and reminders.", ""]

    lines += ["## Timing feedback (learned policy)", "", "| | First half | Second half |", "|---|---|---|"]
    for kind in ("nudge", "reminder"):
        for verdict in ("ok", "too_early", "too_late"):
            lines.append(f"| {kind} {verdict} | {timing.get(f'{kind}_first_{verdict}', 0)} | "
                         f"{timing.get(f'{kind}_second_{verdict}', 0)} |")
    return "\n".join(lines) + "\n"


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
