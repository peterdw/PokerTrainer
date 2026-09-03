"""Speler-entiteit: chips, kaarten en de toestand binnen één hand."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cards import Card

if TYPE_CHECKING:
    from .strategies import DecisionStrategy


class Player:
    def __init__(self, name: str, chips: int, strategy: "DecisionStrategy", is_human: bool = False) -> None:
        self.name = name
        self.chips = chips
        self.strategy = strategy
        self.is_human = is_human
        self.seat = -1
        self.hole_cards: list[Card] = []
        self.folded = False
        self.all_in = False
        self.bet_this_street = 0
        self.invested_this_hand = 0
        self.has_acted = False

    # --- toestand -----------------------------------------------------------
    def reset_for_hand(self) -> None:
        self.hole_cards = []
        self.folded = False
        self.all_in = False
        self.bet_this_street = 0
        self.invested_this_hand = 0
        self.has_acted = False

    def reset_for_street(self) -> None:
        self.bet_this_street = 0
        self.has_acted = False

    @property
    def is_contender(self) -> bool:
        """Maakt nog kans op de pot (niet gefold)."""
        return not self.folded

    @property
    def can_act(self) -> bool:
        return not self.folded and not self.all_in

    # --- chips --------------------------------------------------------------
    def commit(self, amount: int) -> int:
        """Zet chips in (nooit meer dan de stack). Geeft het echte bedrag terug."""
        actual = min(amount, self.chips)
        self.chips -= actual
        self.bet_this_street += actual
        self.invested_this_hand += actual
        if self.chips == 0:
            self.all_in = True
        return actual

    def post_ante(self, amount: int) -> int:
        """Ante telt mee in de pot, maar niet als inzet in de eerste straat."""
        actual = min(amount, self.chips)
        self.chips -= actual
        self.invested_this_hand += actual
        if self.chips == 0:
            self.all_in = True
        return actual

    def receive(self, amount: int) -> None:
        self.chips += amount

    def fold(self) -> None:
        self.folded = True

    def __repr__(self) -> str:
        return f"Player({self.name}, {self.chips})"
