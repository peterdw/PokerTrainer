"""Acties van een speler tijdens een inzetronde.

Patroon: Command. Elke actie is een object dat zichzelf valideert en uitvoert
op de ``BettingRound``. De ``CommandFactory`` vertaalt een gevraagde ``Action``
(van mens of bot) naar het juiste commando.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .betting import BettingRound
    from .players import Player


class ActionType(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all-in"

    @property
    def dutch(self) -> str:
        return {
            ActionType.FOLD: "past (fold)",
            ActionType.CHECK: "checkt",
            ActionType.CALL: "callt",
            ActionType.BET: "bet",
            ActionType.RAISE: "raiset naar",
            ActionType.ALL_IN: "gaat all-in voor",
        }[self]

    @property
    def imperative(self) -> str:
        return {
            ActionType.FOLD: "FOLD (pas)",
            ActionType.CHECK: "CHECK",
            ActionType.CALL: "CALL",
            ActionType.BET: "BET naar",
            ActionType.RAISE: "RAISE naar",
            ActionType.ALL_IN: "ALL-IN",
        }[self]


@dataclass(frozen=True)
class Action:
    """Gevraagde of uitgevoerde actie.

    Voor BET/RAISE/ALL_IN is ``amount`` het totale bedrag in deze straat
    ("raise naar"); voor CALL het bijgelegde bedrag.
    """

    type: ActionType
    amount: int = 0

    def __str__(self) -> str:
        if self.amount and self.type is not ActionType.CHECK:
            return f"{self.type.dutch} {self.amount}"
        return self.type.dutch


@dataclass(frozen=True)
class LegalActions:
    """Wat mag deze speler nu doen? (officiële no-limit regels)"""

    can_check: bool
    call_amount: int  # extra chips om te callen (0 = check mogelijk)
    can_raise: bool
    min_raise_to: int  # minimale totale inzet na een bet/raise
    max_raise_to: int  # stack + reeds ingezet = all-in

    @property
    def can_fold(self) -> bool:
        return not self.can_check


class IllegalActionError(ValueError):
    pass


class ActionCommand(ABC):
    @abstractmethod
    def execute(self, betting_round: "BettingRound", player: "Player") -> Action:
        """Voert uit en geeft de genormaliseerde actie terug (voor het logboek)."""


class FoldCommand(ActionCommand):
    def execute(self, betting_round: "BettingRound", player: "Player") -> Action:
        player.fold()
        betting_round.register_fold(player)
        return Action(ActionType.FOLD)


class CheckCommand(ActionCommand):
    def execute(self, betting_round: "BettingRound", player: "Player") -> Action:
        legal = betting_round.legal_actions(player)
        if not legal.can_check:
            raise IllegalActionError(f"Checken kan niet; er ligt een inzet van {betting_round.current_bet}.")
        betting_round.register_passive(player)
        return Action(ActionType.CHECK)


class CallCommand(ActionCommand):
    def execute(self, betting_round: "BettingRound", player: "Player") -> Action:
        legal = betting_round.legal_actions(player)
        if legal.call_amount == 0:
            raise IllegalActionError("Er is niets om te callen; check in plaats daarvan.")
        paid = player.commit(legal.call_amount)
        betting_round.register_passive(player)
        if player.all_in:
            return Action(ActionType.ALL_IN, player.bet_this_street)
        return Action(ActionType.CALL, paid)


class RaiseCommand(ActionCommand):
    """Bet of raise 'naar' een totaalbedrag in deze straat."""

    def __init__(self, raise_to: int) -> None:
        self._raise_to = raise_to

    def execute(self, betting_round: "BettingRound", player: "Player") -> Action:
        legal = betting_round.legal_actions(player)
        if not legal.can_raise:
            raise IllegalActionError("Raisen is nu niet toegestaan (de actie is niet heropend).")
        if self._raise_to > legal.max_raise_to:
            raise IllegalActionError(f"Je hebt maar {legal.max_raise_to} in totaal beschikbaar.")
        if self._raise_to < legal.min_raise_to and self._raise_to != legal.max_raise_to:
            raise IllegalActionError(
                f"Minimale raise is naar {legal.min_raise_to} (een raise moet minstens even groot "
                "zijn als de vorige bet of raise)."
            )
        was_bet = betting_round.current_bet == 0
        player.commit(self._raise_to - player.bet_this_street)
        betting_round.register_raise(player)
        if player.all_in:
            return Action(ActionType.ALL_IN, player.bet_this_street)
        return Action(ActionType.BET if was_bet else ActionType.RAISE, player.bet_this_street)


class AllInCommand(ActionCommand):
    def execute(self, betting_round: "BettingRound", player: "Player") -> Action:
        legal = betting_round.legal_actions(player)
        total = legal.max_raise_to
        if total > betting_round.current_bet and legal.can_raise:
            return RaiseCommand(total).execute(betting_round, player)
        player.commit(player.chips)
        betting_round.register_passive(player)
        return Action(ActionType.ALL_IN, player.bet_this_street)


class CommandFactory:
    @staticmethod
    def create(action: Action) -> ActionCommand:
        if action.type is ActionType.FOLD:
            return FoldCommand()
        if action.type is ActionType.CHECK:
            return CheckCommand()
        if action.type is ActionType.CALL:
            return CallCommand()
        if action.type in (ActionType.BET, ActionType.RAISE):
            return RaiseCommand(action.amount)
        if action.type is ActionType.ALL_IN:
            return AllInCommand()
        raise IllegalActionError(f"Onbekende actie: {action}")
