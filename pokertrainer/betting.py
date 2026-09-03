"""Eén inzetronde (straat) volgens de officiële no-limit toernooiregels.

Regels die hier worden afgedwongen:
- Een raise moet minstens even groot zijn als de vorige bet of raise in deze straat.
- Een all-in die kleiner is dan een volledige raise heropent de actie NIET voor
  spelers die al gehandeld hebben: zij mogen alleen nog callen of folden.
- De big blind heeft preflop de "optie" om te checken of te raisen.
- De ronde eindigt zodra iedereen die nog kan handelen evenveel heeft ingezet.
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Sequence

from .actions import Action, ActionType, CommandFactory, IllegalActionError, LegalActions
from .context import DecisionContext
from .events import EventBus, Message, PlayerActed
from .players import Player

ContextFactory = Callable[[Player, LegalActions], DecisionContext]


class BettingRound:
    def __init__(
        self,
        players_in_order: Sequence[Player],
        big_blind: int,
        bus: EventBus,
        street: str,
        context_factory: ContextFactory,
        pot_provider: Callable[[], int],
        current_bet: int = 0,
    ) -> None:
        self._order = list(players_in_order)
        self._big_blind = big_blind
        self._bus = bus
        self._street = street
        self._context_factory = context_factory
        self._pot_provider = pot_provider
        self.current_bet = current_bet
        self.min_raise_increment = big_blind
        self.last_aggressor: Player | None = None
        self._raise_locked: set[Player] = set()
        self._queue: deque[Player] = deque(p for p in self._order if p.can_act)

    # --- regels -------------------------------------------------------------
    def legal_actions(self, player: Player) -> LegalActions:
        call_amount = min(self.current_bet - player.bet_this_street, player.chips)
        max_raise_to = player.chips + player.bet_this_street
        if self.current_bet == 0:
            min_raise_to = self._big_blind
        else:
            min_raise_to = self.current_bet + self.min_raise_increment
        can_raise = player not in self._raise_locked and max_raise_to > self.current_bet
        return LegalActions(
            can_check=call_amount == 0,
            call_amount=call_amount,
            can_raise=can_raise,
            min_raise_to=min(min_raise_to, max_raise_to),
            max_raise_to=max_raise_to,
        )

    def register_fold(self, player: Player) -> None:
        player.has_acted = True

    def register_passive(self, player: Player) -> None:
        player.has_acted = True

    def register_raise(self, player: Player) -> None:
        raise_size = player.bet_this_street - self.current_bet
        is_full_raise = raise_size >= self.min_raise_increment
        self.current_bet = player.bet_this_street
        player.has_acted = True
        if is_full_raise:
            self.min_raise_increment = raise_size
            self.last_aggressor = player
            self._raise_locked.clear()
        else:
            for other in self._order:
                if other is not player and other.has_acted and other.can_act:
                    self._raise_locked.add(other)
        self._requeue_after(player)

    def _requeue_after(self, actor: Player) -> None:
        index = self._order.index(actor)
        rotated = self._order[index + 1 :] + self._order[:index]
        self._queue = deque(p for p in rotated if p.can_act)

    # --- verloop ------------------------------------------------------------
    def _contenders(self) -> list[Player]:
        return [p for p in self._order if p.is_contender]

    def _others_can_respond(self, player: Player) -> bool:
        return any(p is not player and p.can_act for p in self._order)

    def run(self) -> None:
        while self._queue:
            player = self._queue.popleft()
            if not player.can_act:
                continue
            if len(self._contenders()) == 1:
                break
            matched = player.bet_this_street >= self.current_bet
            if matched and player.has_acted:
                continue
            if matched and not self._others_can_respond(player):
                continue  # iedereen is all-in en er is niets meer te beslissen
            executed = self._act(player)
            self._bus.publish(PlayerActed(player, executed, self._street, self._pot_provider()))
            if len(self._contenders()) == 1:
                break

    def _act(self, player: Player) -> Action:
        while True:
            context = self._context_factory(player, self.legal_actions(player))
            requested = player.strategy.decide(context)
            try:
                return CommandFactory.create(requested).execute(self, player)
            except IllegalActionError as error:
                if player.is_human:
                    self._bus.publish(Message(f"Ongeldige actie: {error}"))
                    continue
                return self._safe_fallback(player)

    def _safe_fallback(self, player: Player) -> Action:
        legal = self.legal_actions(player)
        fallback = Action(ActionType.CHECK) if legal.can_check else Action(ActionType.FOLD)
        return CommandFactory.create(fallback).execute(self, player)
