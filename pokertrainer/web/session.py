"""Eén spelsessie voor de browser.

De spelmotor is synchroon en vraagt de mens om een beslissing met een
blokkerende aanroep. Daarom draait elke tafel in een eigen achtergrondthread:
gebeurtenissen gaan via ``emit`` naar een logboek dat de server streamt, en de
antwoorden van de browser komen binnen via een postvak (``queue.Queue``).
"""

from __future__ import annotations

import queue
import random
import threading
import uuid
from dataclasses import dataclass
from typing import Callable

from ..coach import Coach
from ..console import QuitRequested
from ..equity import EquityCalculator
from ..evaluation import HandEvaluator
from ..events import EventBus
from ..factory import BOT_PROFILES, create_bot_lineup
from ..lessons import PracticeLesson, TournamentLesson
from ..players import Player
from ..session import Tournament
from ..starting_hands import StartingHandModel, hand_model
from ..tournament import TournamentConfig, championship_sit_and_go, practice_table
from ..view import SessionStats
from .adapters import PacedStrategy, PacingObserver, Tempo, WebHumanStrategy, WebIO
from .presenter import TablePresenter, level_json


@dataclass(frozen=True)
class TablePreset:
    key: str
    title: str
    bot_keys: tuple[str, ...]
    auto_advice: bool
    max_hands: int | None
    config: Callable[[], TournamentConfig]


TABLE_PRESETS: dict[str, TablePreset] = {
    PracticeLesson.key: TablePreset(
        PracticeLesson.key,
        PracticeLesson.title,
        tuple(PracticeLesson.bot_keys),
        PracticeLesson.auto_advice,
        PracticeLesson.max_hands,
        practice_table,
    ),
    TournamentLesson.key: TablePreset(
        TournamentLesson.key,
        TournamentLesson.title,
        tuple(TournamentLesson.bot_keys),
        TournamentLesson.auto_advice,
        TournamentLesson.max_hands,
        championship_sit_and_go,
    ),
}


class SessionBusy(RuntimeError):
    """De gevraagde stap past niet bij de toestand van de sessie."""


class WebSession:
    def __init__(self, player_name: str, seed: int | None = None, model_key: str | None = None) -> None:
        self.id = uuid.uuid4().hex
        self.hand_model: StartingHandModel = hand_model(model_key)
        name = (player_name or "").strip() or "Jij"
        if name in {profile.name for profile in BOT_PROFILES.values()}:
            name = f"{name} (jij)"
        self.player_name = name
        self._rng = random.Random(seed)
        self._evaluator = HandEvaluator()
        self._equity = EquityCalculator(self._evaluator, self._rng, samples=300)
        self._events: list[dict] = []
        self._condition = threading.Condition()
        self._inbox: "queue.Queue[dict | None]" = queue.Queue()
        self._tempo = Tempo()
        self._human: WebHumanStrategy | None = None
        self._thread: threading.Thread | None = None

    # --- gebeurtenissenlog --------------------------------------------------
    def emit(self, payload: dict) -> None:
        with self._condition:
            payload["id"] = len(self._events)
            self._events.append(payload)
            self._condition.notify_all()

    def events_since(self, cursor: int, timeout: float = 0.0) -> list[dict]:
        """Alle gebeurtenissen vanaf ``cursor``; wacht hoogstens ``timeout`` s op nieuwe."""
        with self._condition:
            if len(self._events) <= cursor and timeout > 0:
                self._condition.wait(timeout)
            return list(self._events[cursor:])

    # --- besturing ----------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def finished(self) -> bool:
        return self._thread is not None and not self._thread.is_alive()

    def start_table(self, lesson_key: str, speed: float = 1.0) -> None:
        if self._thread is not None:
            raise SessionBusy("Deze sessie heeft al een tafel; start een nieuwe sessie.")
        preset = TABLE_PRESETS[lesson_key]
        self.set_speed(speed)
        self._thread = threading.Thread(target=self._play, args=(preset,), name=f"tafel-{self.id[:8]}", daemon=True)
        self._thread.start()

    def set_speed(self, speed: float) -> None:
        """1.0 = normaal tempo, 2.0 = dubbel zo snel, 0 = geen pauzes (tests)."""
        speed = max(0.0, min(float(speed), 10.0))
        self._tempo.factor = 0.0 if speed == 0 else 1.0 / speed

    def act(self, answer: dict) -> None:
        if self._human is None or self._human.pending is None:
            raise SessionBusy("Je bent nu niet aan de beurt.")
        self._inbox.put(dict(answer))

    def advice(self) -> dict:
        advice = self._human.advise() if self._human is not None else None
        if advice is None:
            raise SessionBusy("Er is nu geen beslissing om advies over te geven.")
        return advice

    def quit(self) -> None:
        self._tempo.stop()
        self._inbox.put(None)

    # --- de tafel -----------------------------------------------------------
    def _play(self, preset: TablePreset) -> None:
        config = preset.config()
        bus = EventBus()
        coach = Coach(self._evaluator, self._equity, WebIO(self.emit), self.player_name, self._rng, self.hand_model)
        self._human = WebHumanStrategy(self.emit, self._inbox, coach, preset.auto_advice)
        human = Player(self.player_name, config.starting_stack, self._human, is_human=True)
        bots = create_bot_lineup(
            list(preset.bot_keys), config.starting_stack, self._evaluator, self._rng, self.hand_model
        )
        for bot in bots:
            bot.strategy = PacedStrategy(bot.strategy, self._tempo, bus, self._rng)
        players = [human, *bots]
        self._rng.shuffle(players)

        styles = {BOT_PROFILES[key].name: BOT_PROFILES[key].description for key in preset.bot_keys}
        styles[human.name] = "dat ben jij"
        stats = SessionStats(self.player_name)
        presenter = TablePresenter(self.emit, players, self.player_name, styles)
        bus.subscribe(presenter)  # eerst de browser informeren ...
        bus.subscribe(coach)
        bus.subscribe(stats)
        bus.subscribe(PacingObserver(self._tempo))  # ... en dan pas pauzeren
        tournament = Tournament(config, players, bus, self._evaluator, self._rng)

        self.emit(
            {
                "type": "table_started",
                "lesson": preset.key,
                "title": preset.title,
                "auto_advice": preset.auto_advice,
                "max_hands": preset.max_hands,
                "human": self.player_name,
                "model": {"key": self.hand_model.key, "name": self.hand_model.name},
                "config": {
                    "name": config.name,
                    "starting_stack": config.starting_stack,
                    "hands_per_level": config.hands_per_level,
                    "rebuys": config.rebuys,
                    "levels": [level_json(level) for level in config.levels],
                },
                "state": presenter.snapshot(),
            }
        )
        outcome = "finished"
        try:
            tournament.run(preset.max_hands)
        except QuitRequested:
            outcome = "quit"
        except Exception as error:  # noqa: BLE001 - liever tonen dan stil vastlopen
            outcome = "error"
            self.emit({"type": "message", "text": f"Interne fout: {error!r}"})
        finally:
            self.emit(
                {
                    "type": "lesson_finished",
                    "outcome": outcome,
                    "chips": human.chips,
                    "won": tournament.ranking[:1] == [human],
                    "hands": stats.hands,
                    "hands_won": stats.hands_won,
                    "folded_preflop": stats.folded_preflop,
                    "showdowns": stats.showdowns_seen,
                    "chips_won": stats.chips_won,
                    "summary": stats.summary(),
                    "ranking": [p.name for p in tournament.ranking],
                }
            )
