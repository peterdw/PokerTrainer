"""Een toernooi: reeks handen met stijgende blinds tot er één speler overblijft."""

from __future__ import annotations

import random
from typing import Sequence

from .dealer import HandRunner
from .evaluation import HandEvaluator
from .events import BlindLevelChanged, EventBus, Message, PlayerEliminated, TournamentFinished
from .players import Player
from .table import Table
from .tournament import TournamentConfig


class Tournament:
    def __init__(
        self,
        config: TournamentConfig,
        players: Sequence[Player],
        bus: EventBus,
        evaluator: HandEvaluator,
        rng: random.Random | None = None,
        stop_when_human_busts: bool = True,
    ) -> None:
        self._config = config
        self._players = list(players)
        self._bus = bus
        self._rng = rng or random.Random()
        self._stop_when_human_busts = stop_when_human_busts
        self._table = Table(self._players)
        self._runner = HandRunner(self._table, bus, evaluator, self._rng, config.big_blind_ante)
        self.hands_played = 0
        self.ranking: list[Player] = []  # van laatst uitgeschakeld naar eerst

    @property
    def players(self) -> list[Player]:
        return list(self._players)

    def run(self, max_hands: int | None = None) -> Player | None:
        level_index = 0
        self._bus.publish(BlindLevelChanged(self._config.level_at(0), 1))
        while len(self._table.players_with_chips()) > 1:
            if max_hands is not None and self.hands_played >= max_hands:
                return None
            new_index = self.hands_played // self._config.hands_per_level
            if new_index != level_index and new_index < len(self._config.levels):
                level_index = new_index
                self._bus.publish(BlindLevelChanged(self._config.level_at(level_index), level_index + 1))
            self.hands_played += 1
            alive_before = self._table.players_with_chips()
            self._runner.play_hand(self.hands_played, self._config.level_at(level_index))
            if self._handle_eliminations(alive_before):
                return None
            self._table.move_button()
        winner = self._table.players_with_chips()[0]
        self.ranking.insert(0, winner)
        self._bus.publish(TournamentFinished(winner, tuple(self.ranking)))
        return winner

    def _handle_eliminations(self, alive_before: list[Player]) -> bool:
        """Publiceert uitschakelingen (of rebuys); True als het spel moet stoppen."""
        busted = [p for p in alive_before if p.chips == 0]
        if self._config.rebuys:
            for player in busted:
                player.receive(self._config.starting_stack)
                self._bus.publish(Message(f"{player.name} koopt opnieuw in voor {self._config.starting_stack}."))
            return False
        remaining = len(self._table.players_with_chips())
        for player in sorted(busted, key=lambda p: p.invested_this_hand):
            self.ranking.insert(0, player)
            self._bus.publish(PlayerEliminated(player, remaining + 1))
            if player.is_human and self._stop_when_human_busts:
                return True
        return False
