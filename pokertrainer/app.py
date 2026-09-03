"""Het hoofdprogramma.

Patroon: Facade. ``PokerTrainer`` verbergt de opbouw van evaluator, equity-
berekening, lessen en console achter één eenvoudige ``run()``.
"""

from __future__ import annotations

import random

from .console import ConsoleIO, QuitRequested, UserIO
from .equity import EquityCalculator
from .evaluation import HandEvaluator
from .lessons import LessonFactory, TrainerServices
from .starting_hands import HAND_MODELS, hand_model

BANNER = """
  ♠ ♥ ♦ ♣   POKER TRAINER   ♣ ♦ ♥ ♠
  Leer No-Limit Texas Hold'em zoals het op kampioenschappen wordt gespeeld.
"""


class PokerTrainer:
    def __init__(self, io: UserIO | None = None, seed: int | None = None, coach_method: str | None = None) -> None:
        self._io = io or ConsoleIO()
        rng = random.Random(seed)
        evaluator = HandEvaluator()
        self._services = TrainerServices(
            io=self._io,
            rng=rng,
            evaluator=evaluator,
            equity=EquityCalculator(evaluator, rng, samples=300),
            player_name="Jij",
            hand_model=hand_model(coach_method),
        )

    def run(self) -> None:
        self._io.show(BANNER)
        name = self._io.ask("Hoe heet je? [Jij]: ").strip()
        if name and name.lower() != "q":
            self._services.player_name = name
        keys = LessonFactory.keys()
        while True:
            self._io.show("")
            self._io.show("Wat wil je doen?")
            for number, key in enumerate(keys, start=1):
                self._io.show(f"  {number}. {LessonFactory.title(key)}")
            switch, stop = len(keys) + 1, len(keys) + 2
            self._io.show(f"  {switch}. Coachmethode wisselen (nu: {self._services.hand_model.name})")
            self._io.show(f"  {stop}. Stoppen")
            choice = self._io.ask("Keuze: ").strip().lower()
            if choice in ("q", str(stop)):
                self._io.show("Tot de volgende keer. Veel succes aan de tafels!")
                return
            if choice == str(switch):
                self._switch_coach_method()
                continue
            if choice.isdigit() and 1 <= int(choice) <= len(keys):
                try:
                    LessonFactory.create(keys[int(choice) - 1], self._services).run()
                except QuitRequested:
                    pass
            else:
                self._io.show("Kies een getal uit het menu.")

    def _switch_coach_method(self) -> None:
        models = list(HAND_MODELS.values())
        index = models.index(self._services.hand_model)
        self._services.hand_model = models[(index + 1) % len(models)]
        model = self._services.hand_model
        self._io.show(f"Coachmethode: {model.name}. {model.description}")
