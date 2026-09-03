"""Opdrachtregelopties voor de browserversie (gedeeld door ``main.py --web`` en
``python -m pokertrainer.web``)."""

from __future__ import annotations

import argparse
from typing import Sequence

from ..starting_hands import DEFAULT_MODEL_KEY, HAND_MODELS


def add_web_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1", help="adres om op te luisteren (standaard 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="poort (standaard 8765, 0 = willekeurig)")
    parser.add_argument("--no-browser", action="store_true", help="open niet automatisch een browservenster")
    parser.add_argument(
        "--coach",
        choices=list(HAND_MODELS),
        default=DEFAULT_MODEL_KEY,
        help="coachmethode voor starthanden: beginner (Chen-formule) of gevorderd (rangetabel per positie); "
        "in de browser per tafel te kiezen",
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pokertrainer.web", description="Poker Trainer in de browser")
    add_web_arguments(parser)
    args = parser.parse_args(argv)
    from .server import serve

    serve(args.host, args.port, open_browser=not args.no_browser, default_model=args.coach)
