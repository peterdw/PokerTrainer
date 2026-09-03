"""Quizvragen voor de les handrangschikking.

De consoleles en de browserversie halen hun vragen allebei hier vandaan, zodat
de lesinhoud op één plek staat en beide versies exact dezelfde oefening bieden.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .cards import Card, Deck, parse_cards
from .evaluation import HandCategory, HandEvaluator, HandValue

EXAMPLE_HANDS: dict[HandCategory, str] = {
    HandCategory.ROYAL_FLUSH: "As Ks Qs Js Ts",
    HandCategory.STRAIGHT_FLUSH: "9h 8h 7h 6h 5h",
    HandCategory.FOUR_OF_A_KIND: "Qc Qd Qh Qs 4d",
    HandCategory.FULL_HOUSE: "Jc Jd Jh 8s 8d",
    HandCategory.FLUSH: "Kd 9d 7d 4d 2d",
    HandCategory.STRAIGHT: "Tc 9d 8h 7s 6c",
    HandCategory.THREE_OF_A_KIND: "7c 7d 7h Ks 2d",
    HandCategory.TWO_PAIR: "Ac Ad 9h 9s 5c",
    HandCategory.ONE_PAIR: "Tc Td Ah 6s 3d",
    HandCategory.HIGH_CARD: "Ad Jc 8h 5s 2c",
}


@dataclass(frozen=True)
class RankingQuestion:
    """Zeven kaarten; de speler moet de categorie van de beste vijf herkennen."""

    cards: tuple[Card, ...]
    value: HandValue


@dataclass(frozen=True)
class ShowdownQuestion:
    """Twee handen en een board; wie wint, of is het een gedeelde pot?"""

    board: tuple[Card, ...]
    hand_a: tuple[Card, ...]
    hand_b: tuple[Card, ...]
    value_a: HandValue
    value_b: HandValue

    @property
    def correct(self) -> int:
        """1 = speler A, 2 = speler B, 3 = gedeelde pot."""
        if self.value_a > self.value_b:
            return 1
        if self.value_b > self.value_a:
            return 2
        return 3


class QuizGenerator:
    def __init__(self, rng: random.Random, evaluator: HandEvaluator) -> None:
        self._rng = rng
        self._evaluator = evaluator

    def ranking_questions(self, count: int) -> list[RankingQuestion]:
        asked: set[HandCategory] = set()
        questions = []
        for _ in range(count):
            question = self.ranking_question(asked)
            asked.add(question.value.category)
            questions.append(question)
        return questions

    def ranking_question(self, asked: set[HandCategory]) -> RankingQuestion:
        """Wisselt willekeurige handen af met opgebouwde handen uit zeldzame categorieën,
        zodat de quiz niet alleen 'een paar' en 'hoge kaart' toont."""
        rng, evaluator = self._rng, self._evaluator
        if len(asked) % 2 == 1:
            unseen = [category for category in HandCategory if category not in asked]
            base = parse_cards(EXAMPLE_HANDS[rng.choice(unseen)])
            deck = Deck(rng)
            deck.remove(base)
            cards = base + deck.deal(2)
            rng.shuffle(cards)
            return RankingQuestion(tuple(cards), evaluator.evaluate(cards))
        for _ in range(20):
            cards = Deck(rng).deal(7)
            value = evaluator.evaluate(cards)
            if value.category not in asked:
                break
        return RankingQuestion(tuple(cards), value)

    def showdown_question(self) -> ShowdownQuestion:
        deck = Deck(self._rng)
        hand_a, hand_b, board = deck.deal(2), deck.deal(2), deck.deal(5)
        return ShowdownQuestion(
            tuple(board),
            tuple(hand_a),
            tuple(hand_b),
            self._evaluator.best_hand(hand_a, board),
            self._evaluator.best_hand(hand_b, board),
        )
