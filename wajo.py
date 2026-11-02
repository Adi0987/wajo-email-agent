"""Wajo email agent.

    python3 wajo.py         open the assistant in your browser (same as `ui`)
    python3 wajo.py try     the assistant in your terminal
    python3 wajo.py eval    run the full evaluation and print the results
    python3 wajo.py test    run the unit tests
    python3 wajo.py tune    re-pick the learning thresholds on tuning seeds

In the browser, Admin lets you choose where emails come from and plant your own.
"""
import argparse
import sys
import unittest


def session_settings(args) -> dict:
    """Only the options the user set; everything else uses the best defaults for this machine."""
    settings = {"persona": args.persona, "count": args.count}
    if args.offline:
        settings.update(source="synthetic", llm="offline")
    return {k: v for k, v in settings.items() if v is not None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command")

    for name, text in (("ui", "open the assistant in your browser"), ("try", "the assistant in your terminal")):
        cmd = commands.add_parser(name, help=text)
        cmd.add_argument("--persona", help="Enron mailbox to use (default kaminski-v)")
        cmd.add_argument("--count", type=int, help="number of emails (default 20)")
        cmd.add_argument("--offline", action="store_true", help="synthetic inbox, no API key needed")
    commands.choices["try"].add_argument("--details", action="store_true", help="also show each safety check's result")
    for name, text in (("eval", "run the evaluation"), ("tune", "re-pick learning thresholds")):
        cmd = commands.add_parser(name, help=text)
        cmd.add_argument("--llm", choices=["deepseek", "stub"], default="deepseek",
                         help="deepseek (cached, no key needed) or stub (offline worst case)")
    commands.add_parser("test", help="run the unit tests")

    args = parser.parse_args()
    if args.command in (None, "ui"):
        from app.web import serve
        serve(session_settings(args) if args.command else {})
    elif args.command == "try":
        from app.cli import run
        run(session_settings(args), args.details)
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
