"""Terminal colors for `wajo.py try`. Off when output isn't a terminal or NO_COLOR is set."""

import os
import sys

from policy.models import Level

ON = sys.stdout.isatty() and "NO_COLOR" not in os.environ
BOLD, DIM, REVERSE = "1", "2", "7"
RED, GREEN, YELLOW, BLUE, CYAN = "31", "32", "33", "34", "36"
LEVEL_COLOR = {Level.SILENT: GREEN, Level.NOTIFY: CYAN, Level.ASK: YELLOW, Level.ESCALATE: RED}


def paint(text: str, *codes: str) -> str:
    return f"\033[{';'.join(codes)}m{text}\033[0m" if ON and codes else text


def badge(level: Level) -> str:
    """The level as a colored label, e.g. ` ASK ` on yellow."""
    return paint(f" {level.name} ", BOLD, REVERSE, LEVEL_COLOR[level])


def level_word(level: Level) -> str:
    return paint(level.name.title(), LEVEL_COLOR[level])
