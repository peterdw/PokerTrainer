"""Alles wat een speler (mens of bot) mag weten op het moment dat hij moet beslissen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from .actions import LegalActions
from .cards import Card

if TYPE_CHECKING:
    from .players import Player


@dataclass(frozen=True)
class OpponentInfo:
    name: str
    chips: int
    bet_this_street: int
    folded: bool
    all_in: bool
    position: str


@dataclass(frozen=True)
class DecisionContext:
    player: "Player"
    hole_cards: tuple[Card, ...]
    board: tuple[Card, ...]
    street: str
    pot: int  # alle chips in het midden, inclusief inzetten van deze straat
    current_bet: int
    legal: LegalActions
    big_blind: int
    position: str
    players_to_act_after: int  # hoeveel spelers na mij nog handelen (postflop-volgorde)
    contenders: int  # spelers die nog kans maken op de pot (incl. mijzelf)
    opponents: Sequence[OpponentInfo]

    @property
    def to_call(self) -> int:
        return self.legal.call_amount

    @property
    def stack(self) -> int:
        return self.player.chips

    @property
    def facing_bet(self) -> bool:
        return self.to_call > 0

    @property
    def pot_odds(self) -> float:
        """Aandeel van de pot dat je moet winnen om break-even te callen."""
        if self.to_call == 0:
            return 0.0
        return self.to_call / (self.pot + self.to_call)

    @property
    def active_opponents(self) -> int:
        return self.contenders - 1

    @property
    def stack_in_big_blinds(self) -> float:
        return (self.stack + self.player.bet_this_street) / self.big_blind
