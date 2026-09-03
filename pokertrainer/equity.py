"""Monte-Carlo schatting van de winkans (equity) van een hand."""

from __future__ import annotations

import random
from typing import Sequence

from .cards import Card, Deck
from .evaluation import HandEvaluator


class EquityCalculator:
    def __init__(self, evaluator: HandEvaluator, rng: random.Random | None = None, samples: int = 150) -> None:
        self._evaluator = evaluator
        self._rng = rng or random.Random()
        self._samples = samples

    def estimate(
        self,
        hole_cards: Sequence[Card],
        board: Sequence[Card],
        opponents: int,
        samples: int | None = None,
    ) -> float:
        """Kans (0..1) dat deze hand wint tegen ``opponents`` willekeurige handen."""
        opponents = max(1, opponents)
        runs = samples or self._samples
        known = set(hole_cards) | set(board)
        remaining = [card for card in Deck.full() if card not in known]
        missing_board = 5 - len(board)
        score = 0.0
        for _ in range(runs):
            drawn = self._rng.sample(remaining, missing_board + 2 * opponents)
            full_board = [*board, *drawn[:missing_board]]
            mine = self._evaluator.evaluate([*hole_cards, *full_board])
            best_opponent = None
            tied = 0
            for i in range(opponents):
                start = missing_board + 2 * i
                theirs = self._evaluator.evaluate([*drawn[start : start + 2], *full_board])
                if best_opponent is None or theirs > best_opponent:
                    best_opponent, tied = theirs, 1
                elif theirs == best_opponent:
                    tied += 1
            assert best_opponent is not None
            if mine > best_opponent:
                score += 1.0
            elif mine == best_opponent:
                score += 1.0 / (tied + 1)
        return score / runs
