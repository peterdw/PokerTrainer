"""De straten van een hand: preflop, flop, turn, river, showdown.

Patroon: State. De hand bevindt zich altijd in precies één straat; elke straat
weet hoe ze kaarten deelt en welke straat erna komt. De dealer hoeft dus geen
if/else-ketting over de fase van het spel te bevatten.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .cards import Card, Deck
from .events import CardBurned, CommunityCardsDealt, EventBus, HoleCardsDealt
from .players import Player


@dataclass
class HandContext:
    deck: Deck
    players: list[Player]  # spelers in deze hand, in stoelvolgorde vanaf de small blind
    bus: EventBus
    board: list[Card] = field(default_factory=list)

    @property
    def pot(self) -> int:
        return sum(p.invested_this_hand for p in self.players)

    @property
    def contenders(self) -> list[Player]:
        return [p for p in self.players if p.is_contender]


class Street(ABC):
    name: str = ""
    has_betting: bool = True

    @abstractmethod
    def deal(self, hand: HandContext) -> None: ...

    @abstractmethod
    def next(self) -> "Street | None": ...


class _CommunityStreet(Street):
    cards_to_deal: int = 0

    def deal(self, hand: HandContext) -> None:
        hand.deck.burn()
        hand.bus.publish(CardBurned(self.name))
        new_cards = hand.deck.deal(self.cards_to_deal)
        hand.board.extend(new_cards)
        hand.bus.publish(CommunityCardsDealt(self.name, tuple(new_cards), tuple(hand.board), hand.pot))


class PreFlop(Street):
    name = "preflop"

    def deal(self, hand: HandContext) -> None:
        for _ in range(2):  # officieel: één kaart per keer, rondom de tafel
            for player in hand.players:
                player.hole_cards.append(hand.deck.deal_one())
        for player in hand.players:
            hand.bus.publish(HoleCardsDealt(player, tuple(player.hole_cards)))

    def next(self) -> Street:
        return Flop()


class Flop(_CommunityStreet):
    name = "flop"
    cards_to_deal = 3

    def next(self) -> Street:
        return Turn()


class Turn(_CommunityStreet):
    name = "turn"
    cards_to_deal = 1

    def next(self) -> Street:
        return River()


class River(_CommunityStreet):
    name = "river"
    cards_to_deal = 1

    def next(self) -> Street:
        return Showdown()


class Showdown(Street):
    name = "showdown"
    has_betting = False

    def deal(self, hand: HandContext) -> None:
        return None

    def next(self) -> None:
        return None
