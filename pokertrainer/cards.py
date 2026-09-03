"""Kaarten en het kaartspel.

Patronen:
- Flyweight: er bestaan exact 52 Card-objecten; ``Card.of`` geeft altijd
  dezelfde instantie terug, zodat kaarten goedkoop gedeeld en vergeleken worden.
- Iterator: ``Deck`` is itereerbaar en deelt kaarten uit als een stroom.
"""

from __future__ import annotations

import random
from enum import Enum, IntEnum
from typing import ClassVar, Iterable, Iterator, Sequence


class Suit(Enum):
    CLUBS = "♣"
    DIAMONDS = "♦"
    HEARTS = "♥"
    SPADES = "♠"

    @property
    def dutch_name(self) -> str:
        return {
            Suit.CLUBS: "klaveren",
            Suit.DIAMONDS: "ruiten",
            Suit.HEARTS: "harten",
            Suit.SPADES: "schoppen",
        }[self]


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    @property
    def label(self) -> str:
        return "23456789TJQKA"[self.value - 2]

    @property
    def dutch_name(self) -> str:
        names = {
            Rank.JACK: "boer",
            Rank.QUEEN: "vrouw",
            Rank.KING: "heer",
            Rank.ACE: "aas",
            Rank.TEN: "tien",
        }
        return names.get(self, str(self.value))

    @classmethod
    def from_label(cls, label: str) -> "Rank":
        index = "23456789TJQKA".index(label.upper())
        return cls(index + 2)


class Card:
    """Onveranderlijke speelkaart (Flyweight: één instantie per rank/suit)."""

    __slots__ = ("rank", "suit")
    _pool: ClassVar[dict[tuple[Rank, Suit], "Card"]] = {}

    def __init__(self, rank: Rank, suit: Suit) -> None:
        self.rank = rank
        self.suit = suit

    @classmethod
    def of(cls, rank: Rank, suit: Suit) -> "Card":
        key = (rank, suit)
        card = cls._pool.get(key)
        if card is None:
            card = cls(rank, suit)
            cls._pool[key] = card
        return card

    @classmethod
    def parse(cls, text: str) -> "Card":
        """Maakt een kaart uit notatie zoals ``As`` (schoppen aas) of ``Td``."""
        text = text.strip()
        if len(text) != 2:
            raise ValueError(f"Ongeldige kaartnotatie: {text!r}")
        suit_by_letter = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}
        return cls.of(Rank.from_label(text[0]), suit_by_letter[text[1].lower()])

    def __repr__(self) -> str:
        return f"{self.rank.label}{self.suit.value}"

    __str__ = __repr__

    def __lt__(self, other: "Card") -> bool:
        return self.rank < other.rank

    def __eq__(self, other: object) -> bool:
        return self is other

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))


def parse_cards(text: str) -> list[Card]:
    """``"As Kd"`` -> [A♠, K♦]."""
    return [Card.parse(token) for token in text.split()]


def cards_to_str(cards: Iterable[Card]) -> str:
    return " ".join(str(card) for card in cards)


class Deck:
    """Een geschud spel van 52 kaarten dat kaarten uitdeelt (Iterator)."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._cards: list[Card] = [Card.of(rank, suit) for suit in Suit for rank in Rank]
        self._rng.shuffle(self._cards)
        self._position = 0

    @classmethod
    def full(cls) -> list[Card]:
        return [Card.of(rank, suit) for suit in Suit for rank in Rank]

    def deal(self, count: int = 1) -> list[Card]:
        if self._position + count > len(self._cards):
            raise RuntimeError("Het kaartspel is op.")
        dealt = self._cards[self._position : self._position + count]
        self._position += count
        return dealt

    def deal_one(self) -> Card:
        return self.deal(1)[0]

    def burn(self) -> None:
        """Officieel wordt voor flop, turn en river één kaart weggelegd."""
        self.deal(1)

    def remove(self, cards: Sequence[Card]) -> None:
        """Verwijdert bekende kaarten (gebruikt door de equity-simulatie)."""
        known = set(cards)
        self._cards = [card for card in self._cards if card not in known]

    def __len__(self) -> int:
        return len(self._cards) - self._position

    def __iter__(self) -> Iterator[Card]:
        while len(self) > 0:
            yield self.deal_one()
