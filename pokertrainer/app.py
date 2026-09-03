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

BANNER = """
  ♠ ♥ ♦ ♣   POKER TRAINER   ♣ ♦ ♥ ♠
  Leer No-Limit Texas Hold'em zoals het op kampioenschappen wordt gespeeld.
"""


class PokerTrainer:
    def __init__(self, io: UserIO | None = None, seed: int | None = None) -> None:
        self._io = io or ConsoleIO()
        rng = random.Random(seed)
        evaluator = HandEvaluator()
        self._services = TrainerServices(
            io=self._io,
            rng=rng,
            evaluator=evaluator,
            equity=EquityCalculator(evaluator, rng, samples=300),
            player_name="Jij",
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
            self._io.show(f"  {len(keys) + 1}. Stoppen")
            choice = self._io.ask("Keuze: ").strip().lower()
            if choice in ("q", str(len(keys) + 1)):
                self._io.show("Tot de volgende keer. Veel succes aan de tafels!")
                return
            if choice.isdigit() and 1 <= int(choice) <= len(keys):
                try:
                    LessonFactory.create(keys[int(choice) - 1], self._services).run()
                except QuitRequested:
                    pass
            else:
                self._io.show("Kies een getal uit het menu.")
