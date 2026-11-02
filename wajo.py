"""Wajo email agent.

    python3 wajo.py try     be the user: emails arrive, the agent decides, you answer
    python3 wajo.py eval    run the full evaluation and print the results
    python3 wajo.py test    run the unit tests
    python3 wajo.py tune    re-pick the learning thresholds on tuning seeds
"""
import argparse
import sys
import unittest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    try_cmd = commands.add_parser("try", help="be the user and answer the agent")
    try_cmd.add_argument("--persona", default="kaminski-v", help="Enron mailbox to use (default kaminski-v)")
    try_cmd.add_argument("--count", type=int, default=20, help="number of emails (default 20)")
    try_cmd.add_argument("--offline", action="store_true", help="synthetic inbox, no API key needed")
    try_cmd.add_argument("--details", action="store_true", help="also show each safety check's result")

    for name, text in (("eval", "run the evaluation"), ("tune", "re-pick learning thresholds")):
        cmd = commands.add_parser(name, help=text)
        cmd.add_argument("--llm", choices=["deepseek", "stub"], default="deepseek",
                         help="deepseek (cached, no key needed) or stub (offline worst case)")
    commands.add_parser("test", help="run the unit tests")

    args = parser.parse_args()
    if args.command == "try":
        from eval.interactive import try_agent
        try_agent(args.persona, args.count, args.offline, args.details)
    elif args.command == "eval":
        from eval.run import run_eval
        from eval.transcripts import write_transcripts
        print(run_eval(args.llm))
        print(f"Saved eval/results_{args.llm}.md and {write_transcripts(args.llm)}")
    elif args.command == "tune":
        from eval.tune import tune
        print(tune(args.llm))
    else:
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover("tests", top_level_dir="."))
        sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
