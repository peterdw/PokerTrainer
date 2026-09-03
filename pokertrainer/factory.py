"""Fabrieken voor spelers.

Patroon: Factory Method. ``PlayerFactory.create`` bouwt een speler, maar laat
het maken van de strategie over aan de fabrieksmethode ``create_strategy`` die
elke subklasse anders invult (bot met profiel, of mens met console en coach).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from .coach import Coach
from .console import UserIO
from .equity import EquityCalculator
from .evaluation import HandEvaluator
from .players import Player
from .starting_hands import StartingHandModel
from .strategies import BotProfile, DecisionStrategy, HeuristicBotStrategy, HumanConsoleStrategy

BOT_PROFILES: dict[str, BotProfile] = {
    "rots": BotProfile("rots", "Rots", 0.15, 0.3, "tight-passief: speelt weinig handen en raiset zelden"),
    "maniak": BotProfile("maniak", "Maniak", 0.9, 0.9, "loose-agressief: speelt bijna alles en bet constant"),
    "solide": BotProfile("solide", "Solide", 0.45, 0.65, "tight-agressief: selectief, maar raiset met goede handen"),
    "station": BotProfile("station", "Station", 0.8, 0.1, "calling station: callt veel, raiset bijna nooit"),
    "prof": BotProfile("prof", "Prof", 0.4, 0.75, "solide en agressief, let op pot odds"),
}


class PlayerFactory(ABC):
    def create(self, name: str, chips: int) -> Player:
        return Player(name, chips, self.create_strategy(), is_human=self.is_human)

    @property
    def is_human(self) -> bool:
        return False

    @abstractmethod
    def create_strategy(self) -> DecisionStrategy: ...


class BotPlayerFactory(PlayerFactory):
    def __init__(
        self,
        profile: BotProfile,
        evaluator: HandEvaluator,
        rng: random.Random,
        hand_model: StartingHandModel | None = None,
    ) -> None:
        self._profile = profile
        self._evaluator = evaluator
        self._rng = rng
        self._equity = EquityCalculator(evaluator, rng, samples=100)
        self._hand_model = hand_model

    def create_strategy(self) -> DecisionStrategy:
        return HeuristicBotStrategy(self._profile, self._evaluator, self._equity, self._rng, hand_model=self._hand_model)

    def create_bot(self, chips: int) -> Player:
        return self.create(self._profile.name, chips)


class HumanPlayerFactory(PlayerFactory):
    def __init__(self, io: UserIO, coach: Coach | None, auto_advice: bool) -> None:
        self._io = io
        self._coach = coach
        self._auto_advice = auto_advice

    @property
    def is_human(self) -> bool:
        return True

    def create_strategy(self) -> DecisionStrategy:
        return HumanConsoleStrategy(self._io, self._coach, self._auto_advice)


def create_bot_lineup(
    keys: list[str],
    chips: int,
    evaluator: HandEvaluator,
    rng: random.Random,
    hand_model: StartingHandModel | None = None,
) -> list[Player]:
    return [BotPlayerFactory(BOT_PROFILES[key], evaluator, rng, hand_model).create_bot(chips) for key in keys]
