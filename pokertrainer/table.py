"""De tafel: stoelen en de dealerbutton."""

from __future__ import annotations

from typing import Callable, Iterator, Sequence

from .players import Player


class Table:
    def __init__(self, players: Sequence[Player]) -> None:
        if len(players) < 2:
            raise ValueError("Poker speel je met minstens twee spelers.")
        self._seats = list(players)
        for seat, player in enumerate(self._seats):
            player.seat = seat
        self.button = 0

    @property
    def seats(self) -> list[Player]:
        return list(self._seats)

    def players_with_chips(self) -> list[Player]:
        return [p for p in self._seats if p.chips > 0]

    def clockwise_from(self, seat: int, keep: Callable[[Player], bool] = lambda p: True) -> Iterator[Player]:
        """Spelers vanaf ``seat`` (inclusief) met de klok mee."""
        count = len(self._seats)
        for offset in range(count):
            player = self._seats[(seat + offset) % count]
            if keep(player):
                yield player

    def next_seat_with_chips(self, seat: int) -> int:
        for player in self.clockwise_from(seat + 1, lambda p: p.chips > 0):
            return player.seat
        raise RuntimeError("Geen speler met chips gevonden.")

    def move_button(self) -> None:
        self.button = self.next_seat_with_chips(self.button)

    @staticmethod
    def rotate_after(players: Sequence[Player], anchor: Player) -> list[Player]:
        """Zelfde ring, maar beginnend bij de speler ná ``anchor``."""
        index = list(players).index(anchor)
        ring = list(players)
        return ring[index + 1 :] + ring[: index + 1]

    @staticmethod
    def rotate_from(players: Sequence[Player], anchor: Player) -> list[Player]:
        """Zelfde ring, maar beginnend bij ``anchor`` zelf."""
        index = list(players).index(anchor)
        ring = list(players)
        return ring[index:] + ring[:index]
