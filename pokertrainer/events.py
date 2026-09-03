"""Spelgebeurtenissen en de EventBus.

Patroon: Observer. De spelmotor weet niets van console-uitvoer, coach of
statistieken; hij publiceert alleen gebeurtenissen. Waarnemers abonneren zich.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Sequence

from .cards import Card

if TYPE_CHECKING:
    from .actions import Action
    from .evaluation import HandValue
    from .players import Player
    from .tournament import BlindLevel


@dataclass(frozen=True)
class GameEvent:
    """Basisklasse van alle gebeurtenissen."""


@dataclass(frozen=True)
class HandStarted(GameEvent):
    hand_number: int
    button: "Player"
    level: "BlindLevel"
    players: Sequence["Player"]


@dataclass(frozen=True)
class ForcedBetPosted(GameEvent):
    player: "Player"
    kind: str  # "small blind", "big blind", "ante"
    amount: int


@dataclass(frozen=True)
class HoleCardsDealt(GameEvent):
    player: "Player"
    cards: Sequence[Card]


@dataclass(frozen=True)
class CardBurned(GameEvent):
    """De dealer legt vóór flop, turn of river één kaart blind weg."""

    street: str


@dataclass(frozen=True)
class CommunityCardsDealt(GameEvent):
    street: str
    new_cards: Sequence[Card]
    board: Sequence[Card]
    pot: int


@dataclass(frozen=True)
class PlayerThinking(GameEvent):
    """Een speler is aan de beurt en denkt na (voor markering en tempo in een grafische weergave)."""

    player: "Player"


@dataclass(frozen=True)
class PlayerActed(GameEvent):
    player: "Player"
    action: "Action"
    street: str
    pot: int


@dataclass(frozen=True)
class ShowdownReveal(GameEvent):
    player: "Player"
    cards: Sequence[Card]
    hand: "HandValue"


@dataclass(frozen=True)
class PotAwarded(GameEvent):
    player: "Player"
    amount: int
    reason: str
    hand: "HandValue | None" = None


@dataclass(frozen=True)
class HandFinished(GameEvent):
    hand_number: int
    players: Sequence["Player"]


@dataclass(frozen=True)
class PlayerEliminated(GameEvent):
    player: "Player"
    finishing_place: int


@dataclass(frozen=True)
class BlindLevelChanged(GameEvent):
    level: "BlindLevel"
    level_number: int


@dataclass(frozen=True)
class TournamentFinished(GameEvent):
    winner: "Player"
    ranking: Sequence["Player"] = field(default_factory=tuple)


@dataclass(frozen=True)
class Message(GameEvent):
    text: str


class GameObserver(Protocol):
    def notify(self, event: GameEvent) -> None: ...


class EventBus:
    """Onderwerp (Subject) waarop waarnemers zich abonneren."""

    def __init__(self) -> None:
        self._observers: list[GameObserver] = []

    def subscribe(self, observer: GameObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: GameObserver) -> None:
        self._observers.remove(observer)

    def publish(self, event: GameEvent) -> None:
        for observer in list(self._observers):
            observer.notify(event)
