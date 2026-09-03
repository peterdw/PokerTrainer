"""Startpunt.

- ``python main.py``        console-versie
- ``python main.py --web``  browserversie (opent http://127.0.0.1:8765/)
"""

import argparse
import sys

from pokertrainer.app import PokerTrainer
from pokertrainer.web.cli import add_web_arguments


def _use_utf8_console() -> None:
    """Kaartsymbolen (♠ ♥ ♦ ♣) vragen UTF-8; de Windows-console staat vaak op cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poker Trainer: leer No-Limit Texas Hold'em")
    parser.add_argument("--web", action="store_true", help="start de browserversie in plaats van de console")
    add_web_arguments(parser)  # --host, --port, --no-browser en --coach
    return parser.parse_args(argv)


if __name__ == "__main__":
    _use_utf8_console()
    args = _parse_args(sys.argv[1:])
    if args.web:
        from pokertrainer.web.server import serve

        serve(args.host, args.port, open_browser=not args.no_browser, default_model=args.coach)
    else:
        PokerTrainer(coach_method=args.coach).run()
