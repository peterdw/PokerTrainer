"""Toernooistructuur: blindniveaus en configuratie.

Patroon: Builder. Een toernooistructuur heeft veel optionele onderdelen
(niveaus, antes, startstack, tempo). De builder maakt het samenstellen leesbaar
en valideert het resultaat in één keer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlindLevel:
    small_blind: int
    big_blind: int
    ante: int = 0

    def __str__(self) -> str:
        text = f"{self.small_blind}/{self.big_blind}"
        if self.ante:
            text += f" (big blind ante {self.ante})"
        return text


@dataclass(frozen=True)
class TournamentConfig:
    name: str
    starting_stack: int
    levels: tuple[BlindLevel, ...]
    hands_per_level: int
    big_blind_ante: bool = True
    rebuys: bool = False  # oefentafel: wie bust is, krijgt een nieuwe startstack

    def level_at(self, index: int) -> BlindLevel:
        return self.levels[min(index, len(self.levels) - 1)]


class TournamentConfigBuilder:
    def __init__(self) -> None:
        self._name = "Toernooi"
        self._starting_stack = 5000
        self._levels: list[BlindLevel] = []
        self._hands_per_level = 8
        self._big_blind_ante = True
        self._rebuys = False

    def name(self, name: str) -> "TournamentConfigBuilder":
        self._name = name
        return self

    def starting_stack(self, chips: int) -> "TournamentConfigBuilder":
        self._starting_stack = chips
        return self

    def add_level(self, small_blind: int, big_blind: int, ante: int = 0) -> "TournamentConfigBuilder":
        self._levels.append(BlindLevel(small_blind, big_blind, ante))
        return self

    def hands_per_level(self, hands: int) -> "TournamentConfigBuilder":
        self._hands_per_level = hands
        return self

    def big_blind_ante(self, enabled: bool) -> "TournamentConfigBuilder":
        self._big_blind_ante = enabled
        return self

    def allow_rebuys(self, enabled: bool) -> "TournamentConfigBuilder":
        self._rebuys = enabled
        return self

    def build(self) -> TournamentConfig:
        if not self._levels:
            raise ValueError("Een toernooi heeft minstens één blindniveau nodig.")
        if self._starting_stack <= 0 or self._hands_per_level <= 0:
            raise ValueError("Startstack en handen per niveau moeten positief zijn.")
        for earlier, later in zip(self._levels, self._levels[1:]):
            if later.big_blind < earlier.big_blind:
                raise ValueError("Blinds mogen niet dalen tussen niveaus.")
        return TournamentConfig(
            self._name,
            self._starting_stack,
            tuple(self._levels),
            self._hands_per_level,
            self._big_blind_ante,
            self._rebuys,
        )


def championship_sit_and_go() -> TournamentConfig:
    """Structuur in de stijl van een WSOP-toernooi, versneld voor een sit-and-go.

    Vanaf niveau 4 wordt een big blind ante gespeeld, zoals tegenwoordig
    in vrijwel alle grote toernooien.
    """
    return (
        TournamentConfigBuilder()
        .name("Kampioenschap sit-and-go")
        .starting_stack(5000)
        .hands_per_level(8)
        .add_level(25, 50)
        .add_level(50, 100)
        .add_level(75, 150)
        .add_level(100, 200, ante=200)
        .add_level(150, 300, ante=300)
        .add_level(200, 400, ante=400)
        .add_level(300, 600, ante=600)
        .add_level(400, 800, ante=800)
        .add_level(600, 1200, ante=1200)
        .add_level(800, 1600, ante=1600)
        .add_level(1000, 2000, ante=2000)
        .add_level(1500, 3000, ante=3000)
        .add_level(2000, 4000, ante=4000)
        .add_level(3000, 6000, ante=6000)
        .build()
    )


def practice_table() -> TournamentConfig:
    """Diepe stacks, vaste lage blinds: ideaal om rustig te oefenen."""
    return (
        TournamentConfigBuilder()
        .name("Oefentafel")
        .starting_stack(10000)
        .hands_per_level(1_000_000)
        .add_level(25, 50)
        .big_blind_ante(False)
        .allow_rebuys(True)
        .build()
    )
