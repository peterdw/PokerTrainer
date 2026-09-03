"""Handwaardering: bepaalt de beste vijfkaartencombinatie uit 5 tot 7 kaarten.

Patroon: Chain of Responsibility. Elke ``HandDetector`` herkent één categorie
(van sterk naar zwak). Herkent hij de hand niet, dan geeft hij door aan de
volgende schakel. ``HandEvaluator`` bouwt de keten en biedt een eenvoudige API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Sequence

from .cards import Card, Rank, Suit


class HandCategory(IntEnum):
    HIGH_CARD = 1
    ONE_PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10

    @property
    def dutch_name(self) -> str:
        return {
            HandCategory.HIGH_CARD: "Hoge kaart",
            HandCategory.ONE_PAIR: "Een paar",
            HandCategory.TWO_PAIR: "Twee paar",
            HandCategory.THREE_OF_A_KIND: "Three of a kind (drieling)",
            HandCategory.STRAIGHT: "Straight",
            HandCategory.FLUSH: "Flush",
            HandCategory.FULL_HOUSE: "Full house",
            HandCategory.FOUR_OF_A_KIND: "Four of a kind (carré)",
            HandCategory.STRAIGHT_FLUSH: "Straight flush",
            HandCategory.ROYAL_FLUSH: "Royal flush",
        }[self]

    @property
    def explanation(self) -> str:
        return {
            HandCategory.HIGH_CARD: "geen combinatie; de hoogste kaart telt",
            HandCategory.ONE_PAIR: "twee kaarten van dezelfde waarde",
            HandCategory.TWO_PAIR: "twee verschillende paren",
            HandCategory.THREE_OF_A_KIND: "drie kaarten van dezelfde waarde",
            HandCategory.STRAIGHT: "vijf opeenvolgende waarden (aas mag laag of hoog)",
            HandCategory.FLUSH: "vijf kaarten van dezelfde kleur (suit)",
            HandCategory.FULL_HOUSE: "een drieling plus een paar",
            HandCategory.FOUR_OF_A_KIND: "vier kaarten van dezelfde waarde",
            HandCategory.STRAIGHT_FLUSH: "een straight in één kleur",
            HandCategory.ROYAL_FLUSH: "T-J-Q-K-A in één kleur; de hoogst mogelijke hand",
        }[self]


_PLURAL = {
    Rank.TWO: "tweeën", Rank.THREE: "drieën", Rank.FOUR: "vieren", Rank.FIVE: "vijven",
    Rank.SIX: "zessen", Rank.SEVEN: "zevens", Rank.EIGHT: "achten", Rank.NINE: "negens",
    Rank.TEN: "tienen", Rank.JACK: "boeren", Rank.QUEEN: "vrouwen", Rank.KING: "heren",
    Rank.ACE: "azen",
}


def plural(rank: int) -> str:
    return _PLURAL[Rank(rank)]


@dataclass(frozen=True, order=True)
class HandValue:
    """Vergelijkbare waarde van een pokerhand.

    ``kickers`` bevat de beslissende rangen in afnemend belang, zodat de
    standaard tuple-vergelijking precies de officiële regels volgt.
    """

    category: HandCategory
    kickers: tuple[int, ...]
    best_five: tuple[Card, ...] = field(compare=False, default=())

    def describe(self) -> str:
        cat, k = self.category, self.kickers
        if cat is HandCategory.ROYAL_FLUSH:
            return f"Royal flush in {self.best_five[0].suit.dutch_name}"
        if cat in (HandCategory.STRAIGHT_FLUSH, HandCategory.STRAIGHT, HandCategory.FLUSH):
            return f"{cat.dutch_name}, {Rank(k[0]).dutch_name} hoog"
        if cat is HandCategory.FOUR_OF_A_KIND:
            return f"{cat.dutch_name}, {plural(k[0])}"
        if cat is HandCategory.FULL_HOUSE:
            return f"Full house, {plural(k[0])} vol met {plural(k[1])}"
        if cat is HandCategory.THREE_OF_A_KIND:
            return f"{cat.dutch_name}, {plural(k[0])}"
        if cat is HandCategory.TWO_PAIR:
            return f"Twee paar, {plural(k[0])} en {plural(k[1])}"
        if cat is HandCategory.ONE_PAIR:
            return f"Een paar {plural(k[0])}"
        return f"Hoge kaart, {Rank(k[0]).dutch_name}"


def _straight_high(ranks: set[int]) -> int | None:
    for high in range(14, 5, -1):
        if all(rank in ranks for rank in range(high - 4, high + 1)):
            return high
    if {14, 2, 3, 4, 5} <= ranks:  # het "wiel": A-2-3-4-5
        return 5
    return None


def _straight_cards(cards: Sequence[Card], high: int) -> tuple[Card, ...]:
    wanted = [high - offset for offset in range(5)]
    wanted = [14 if rank == 1 else rank for rank in wanted]
    return tuple(next(card for card in cards if card.rank.value == rank) for rank in wanted)


def _cards_of_rank(cards: Sequence[Card], rank: int, count: int) -> list[Card]:
    return [card for card in cards if card.rank.value == rank][:count]


def _top_kickers(cards: Sequence[Card], exclude: set[int], count: int) -> list[Card]:
    remaining = sorted((c for c in cards if c.rank.value not in exclude), reverse=True)
    return remaining[:count]


def _group_by_suit(cards: Iterable[Card]) -> dict[Suit, list[Card]]:
    by_suit: dict[Suit, list[Card]] = defaultdict(list)
    for card in cards:
        by_suit[card.suit].append(card)
    return by_suit


class HandDetector(ABC):
    """Eén schakel van de keten."""

    def __init__(self) -> None:
        self._next: HandDetector | None = None

    def then(self, successor: "HandDetector") -> "HandDetector":
        self._next = successor
        return successor

    def evaluate(self, cards: Sequence[Card]) -> HandValue:
        found = self._detect(cards)
        if found is not None:
            return found
        if self._next is None:
            raise RuntimeError("Einde van de keten bereikt zonder resultaat.")
        return self._next.evaluate(cards)

    @abstractmethod
    def _detect(self, cards: Sequence[Card]) -> HandValue | None: ...


class StraightFlushDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        best: HandValue | None = None
        for suited in _group_by_suit(cards).values():
            if len(suited) < 5:
                continue
            high = _straight_high({c.rank.value for c in suited})
            if high is None:
                continue
            category = HandCategory.ROYAL_FLUSH if high == 14 else HandCategory.STRAIGHT_FLUSH
            value = HandValue(category, (high,), _straight_cards(suited, high))
            best = value if best is None or value > best else best
        return best


class FourOfAKindDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        counts = Counter(c.rank.value for c in cards)
        quads = [rank for rank, n in counts.items() if n == 4]
        if not quads:
            return None
        quad = max(quads)
        kicker = _top_kickers(cards, {quad}, 1)
        return HandValue(
            HandCategory.FOUR_OF_A_KIND,
            (quad, kicker[0].rank.value),
            tuple(_cards_of_rank(cards, quad, 4) + kicker),
        )


class FullHouseDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        counts = Counter(c.rank.value for c in cards)
        trips = sorted((r for r, n in counts.items() if n >= 3), reverse=True)
        if not trips:
            return None
        top_trips = trips[0]
        pairs = sorted((r for r, n in counts.items() if n >= 2 and r != top_trips), reverse=True)
        if not pairs:
            return None
        pair = pairs[0]
        five = _cards_of_rank(cards, top_trips, 3) + _cards_of_rank(cards, pair, 2)
        return HandValue(HandCategory.FULL_HOUSE, (top_trips, pair), tuple(five))


class FlushDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        best: HandValue | None = None
        for suited in _group_by_suit(cards).values():
            if len(suited) < 5:
                continue
            top = sorted(suited, reverse=True)[:5]
            value = HandValue(HandCategory.FLUSH, tuple(c.rank.value for c in top), tuple(top))
            best = value if best is None or value > best else best
        return best


class StraightDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        high = _straight_high({c.rank.value for c in cards})
        if high is None:
            return None
        return HandValue(HandCategory.STRAIGHT, (high,), _straight_cards(cards, high))


class ThreeOfAKindDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        counts = Counter(c.rank.value for c in cards)
        trips = [r for r, n in counts.items() if n == 3]
        if not trips:
            return None
        trip = max(trips)
        kickers = _top_kickers(cards, {trip}, 2)
        return HandValue(
            HandCategory.THREE_OF_A_KIND,
            (trip, *(k.rank.value for k in kickers)),
            tuple(_cards_of_rank(cards, trip, 3) + kickers),
        )


class TwoPairDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        counts = Counter(c.rank.value for c in cards)
        pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
        if len(pairs) < 2:
            return None
        high, low = pairs[0], pairs[1]
        kicker = _top_kickers(cards, {high, low}, 1)
        five = _cards_of_rank(cards, high, 2) + _cards_of_rank(cards, low, 2) + kicker
        return HandValue(HandCategory.TWO_PAIR, (high, low, kicker[0].rank.value), tuple(five))


class OnePairDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        counts = Counter(c.rank.value for c in cards)
        pairs = [r for r, n in counts.items() if n == 2]
        if not pairs:
            return None
        pair = max(pairs)
        kickers = _top_kickers(cards, {pair}, 3)
        return HandValue(
            HandCategory.ONE_PAIR,
            (pair, *(k.rank.value for k in kickers)),
            tuple(_cards_of_rank(cards, pair, 2) + kickers),
        )


class HighCardDetector(HandDetector):
    def _detect(self, cards: Sequence[Card]) -> HandValue | None:
        top = sorted(cards, reverse=True)[:5]
        return HandValue(HandCategory.HIGH_CARD, tuple(c.rank.value for c in top), tuple(top))


class HandEvaluator:
    """Eenvoudige toegang tot de keten van detectoren."""

    def __init__(self) -> None:
        self._chain = self._build_chain()

    @staticmethod
    def _build_chain() -> HandDetector:
        head = StraightFlushDetector()
        (
            head.then(FourOfAKindDetector())
            .then(FullHouseDetector())
            .then(FlushDetector())
            .then(StraightDetector())
            .then(ThreeOfAKindDetector())
            .then(TwoPairDetector())
            .then(OnePairDetector())
            .then(HighCardDetector())
        )
        return head

    def evaluate(self, cards: Sequence[Card]) -> HandValue:
        if not 5 <= len(cards) <= 7:
            raise ValueError("Een hand wordt bepaald uit 5 tot 7 kaarten.")
        return self._chain.evaluate(list(cards))

    def best_hand(self, hole_cards: Sequence[Card], board: Sequence[Card]) -> HandValue:
        return self.evaluate([*hole_cards, *board])
