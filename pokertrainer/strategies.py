"""Beslisstrategieën.

Patroon: Strategy. Een ``Player`` heeft een ``DecisionStrategy``; de spelmotor
vraagt alleen ``decide(context)`` en weet niet of er een mens, een tight bot of
een maniak achter zit. Bots geven bovendien hun redenering terug, zodat de
coach dezelfde logica kan gebruiken om uit te leggen waarom iets een goede zet is.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Sequence

from .actions import Action, ActionType
from .cards import cards_to_str
from .console import QuitRequested, UserIO
from .context import DecisionContext
from .equity import EquityCalculator
from .evaluation import HandEvaluator
from .push_fold import NASH, PUSH_FOLD_LIMIT, NashPushFold

if TYPE_CHECKING:
    from .coach import Advice


@dataclass(frozen=True)
class Decision:
    action: Action
    reasons: tuple[str, ...]


class DecisionStrategy(ABC):
    @abstractmethod
    def decide(self, context: DecisionContext) -> Action: ...


# --- starthanden: zie starting_hands.py (hier opnieuw geëxporteerd voor bestaande importen) ---
from .starting_hands import (  # noqa: E402
    ChenModel,
    StartingHandModel,
    chen_breakdown,
    chen_explanation,
    chen_score,
    hand_label,
    starting_hand_class,
)

__all__ = [
    "ChenModel", "StartingHandModel", "chen_breakdown", "chen_explanation", "chen_score", "hand_label",
    "starting_hand_class", "BotProfile", "Decision", "DecisionStrategy", "HeuristicBotStrategy",
    "HumanConsoleStrategy", "ScriptedStrategy", "Advisor",
]


@dataclass(frozen=True)
class BotProfile:
    key: str
    name: str
    looseness: float  # 0 = speelt bijna niets, 1 = speelt alles
    aggression: float  # 0 = callt liever, 1 = bet en raiset graag
    description: str


CHEAP_CALL_BB = 3  # een 'gewone' raise: tot ± 3 big blinds bijleggen ...
CHEAP_CALL_STACK_SHARE = 0.12  # ... of tot 12% van je stack


class HeuristicBotStrategy(DecisionStrategy):
    """Speelt op basis van starthandscore (preflop) en winkans vs pot odds (postflop)."""

    def __init__(
        self,
        profile: BotProfile,
        evaluator: HandEvaluator,
        equity: EquityCalculator,
        rng: random.Random | None = None,
        mix: bool = True,
        hand_model: StartingHandModel | None = None,
    ) -> None:
        self._profile = profile
        self._evaluator = evaluator
        self._equity = equity
        self._rng = rng or random.Random()
        self._mix = mix  # False = deterministisch (gebruikt door de coach)
        self._hand_model = hand_model or ChenModel()
        self._push_fold: NashPushFold = NASH

    @property
    def hand_model(self) -> StartingHandModel:
        return self._hand_model

    def decide(self, context: DecisionContext) -> Action:
        return self.reason(context).action

    def reason(self, context: DecisionContext) -> Decision:
        if context.street == "preflop":
            return self._preflop(context)
        return self._postflop(context)

    # --- hulpfuncties -------------------------------------------------------
    def _chance(self, probability: float) -> bool:
        if not self._mix:
            return probability >= 0.5
        return self._rng.random() < probability

    @staticmethod
    def _round_chips(amount: int, big_blind: int) -> int:
        unit = max(1, big_blind // 2)
        return max(unit, int(round(amount / unit)) * unit)

    @staticmethod
    def _raise_to(context: DecisionContext, target: int) -> Action:
        legal = context.legal
        if not legal.can_raise:
            return Action(ActionType.CALL) if context.to_call else Action(ActionType.CHECK)
        if target >= legal.max_raise_to:
            return Action(ActionType.ALL_IN)
        target = max(target, legal.min_raise_to)
        kind = ActionType.BET if context.current_bet == 0 else ActionType.RAISE
        return Action(kind, target)

    def _bet_fraction_of_pot(self, context: DecisionContext, fraction: float) -> Action:
        pot_after_call = context.pot + context.to_call
        target = context.player.bet_this_street + context.to_call + int(fraction * pot_after_call)
        return self._raise_to(context, self._round_chips(target, context.big_blind))

    @staticmethod
    def _call_or_check(context: DecisionContext) -> Action:
        return Action(ActionType.CALL) if context.to_call else Action(ActionType.CHECK)

    @staticmethod
    def _fold_or_check(context: DecisionContext) -> Action:
        return Action(ActionType.CHECK) if context.legal.can_check else Action(ActionType.FOLD)

    # --- preflop ------------------------------------------------------------
    def _preflop(self, context: DecisionContext) -> Decision:
        if context.stack_in_big_blinds <= PUSH_FOLD_LIMIT:
            return self._push_or_fold(context)
        profile = self._profile
        facing_raise = context.current_bet > context.big_blind
        if facing_raise:
            hand = self._hand_model.defend(context.hole_cards, context.position, profile.looseness)
        else:
            hand = self._hand_model.assess(context.hole_cards, context.position, profile.looseness)
        reasons = list(hand.lines)
        bb = context.big_blind

        if not facing_raise:
            callers = sum(1 for o in context.opponents if o.bet_this_street >= bb and o.position != "big blind")
            if hand.premium or (hand.playable and self._chance(0.4 + profile.aggression / 2)):
                reasons.append("Niemand heeft geraised: open met een raise van ± 3 big blinds (+1 per limper).")
                return Decision(self._raise_to(context, (3 + callers) * bb), tuple(reasons))
            if hand.playable:
                reasons.append("Speelbare hand, maar niet sterk genoeg om te raisen: meedoen voor de big blind.")
                return Decision(self._call_or_check(context), tuple(reasons))
            if context.legal.can_check:
                reasons.append("Zwakke hand, maar je mag gratis de flop zien: check.")
                return Decision(Action(ActionType.CHECK), tuple(reasons))
            reasons.append("Te zwak om chips in te zetten: fold.")
            return Decision(Action(ActionType.FOLD), tuple(reasons))

        reasons.append(f"Er ligt een raise naar {context.current_bet}; je moet {context.to_call} bijleggen.")
        if hand.premium:
            if context.legal.can_raise and self._chance(0.3 + profile.aggression * 0.6):
                reasons.append("Premium hand: re-raise (3-bet) naar ± 3x de raise om de pot te bouwen.")
                return Decision(self._raise_to(context, 3 * context.current_bet), tuple(reasons))
            reasons.append("Premium hand: minstens callen.")
            return Decision(self._call_or_check(context), tuple(reasons))
        limit = max(CHEAP_CALL_BB * bb, int(CHEAP_CALL_STACK_SHARE * context.stack))
        if hand.worth_a_call:
            if context.to_call <= limit:
                reasons.append("Goede hand en de call is relatief goedkoop: call en kijk naar de flop.")
                return Decision(self._call_or_check(context), tuple(reasons))
            reasons.append(
                f"De raise is {context.current_bet / bb:g} big blinds; je moet {context.to_call / bb:g} big blinds "
                f"bijleggen ({context.to_call / max(1, context.stack):.0%} van je stack). Deze hand call je alleen "
                f"tegen een gewone raise (tot {CHEAP_CALL_BB} big blinds of {CHEAP_CALL_STACK_SHARE:.0%} van je stack): "
                "te duur, fold."
            )
        else:
            reasons.append("Niet sterk genoeg om een raise te betalen: fold (chips bewaren voor een betere situatie).")
        if context.legal.can_check:
            return Decision(Action(ActionType.CHECK), tuple(reasons))
        return Decision(Action(ActionType.FOLD), tuple(reasons))

    def _push_or_fold(self, context: DecisionContext) -> Decision:
        """Korte stack: all-in of fold volgens de push-or-fold-tabel (duwen, re-shoven of een all-in callen)."""
        looseness = self._profile.looseness
        bb = context.big_blind
        stack_bb = context.stack_in_big_blinds
        live = [opponent for opponent in context.opponents if not opponent.folded]
        callers = sum(1 for opponent in live if not opponent.all_in)
        if context.current_bet > bb:
            aggressor = max(live, key=lambda opponent: opponent.bet_this_street)
            raise_bb = context.current_bet / bb
            if aggressor.all_in or context.to_call >= context.stack:
                # Een all-in (of een inzet die je dekt): callen of folden; effectief staat het kleinste op het spel.
                advice = self._push_fold.calling(context.hole_cards, stack_bb, raise_bb, looseness)
                if advice.go:
                    action = Action(ActionType.ALL_IN) if context.to_call >= context.stack else Action(ActionType.CALL)
                    return Decision(action, advice.lines)
                return Decision(self._fold_or_check(context), advice.lines)
            advice = self._push_fold.reshoving(context.hole_cards, stack_bb, raise_bb, callers, context.position, looseness)
            if advice.go:
                return Decision(Action(ActionType.ALL_IN), advice.lines)
            return Decision(self._fold_or_check(context), advice.lines)
        advice = self._push_fold.pushing(context.hole_cards, stack_bb, context.position, callers, looseness)
        if advice.go:
            return Decision(Action(ActionType.ALL_IN), advice.lines)
        if context.legal.can_check:
            return Decision(Action(ActionType.CHECK), advice.lines + ("Je mag gratis kijken: check in plaats van fold.",))
        return Decision(Action(ActionType.FOLD), advice.lines)

    # --- postflop -----------------------------------------------------------
    def _postflop(self, context: DecisionContext) -> Decision:
        profile = self._profile
        value = self._evaluator.best_hand(context.hole_cards, context.board)
        equity = self._equity.estimate(context.hole_cards, context.board, context.active_opponents)
        reasons = [
            f"Beste hand nu: {value.describe()} ({cards_to_str(value.best_five)}).",
            f"Geschatte winkans tegen {context.active_opponents} tegenstander(s): {equity:.0%}.",
        ]
        if not context.facing_bet:
            if equity >= 0.62 - 0.12 * profile.aggression:
                reasons.append("Je bent waarschijnlijk voor: bet ± 2/3 pot voor waarde (value bet).")
                return Decision(self._bet_fraction_of_pot(context, 0.66), tuple(reasons))
            if context.players_to_act_after <= 1 and self._chance(profile.aggression * 0.25):
                reasons.append("Weinig spelers achter je: een (semi-)bluf van een halve pot kan de pot pakken.")
                return Decision(self._bet_fraction_of_pot(context, 0.5), tuple(reasons))
            reasons.append("Geen sterke hand en niets te betalen: check.")
            return Decision(Action(ActionType.CHECK), tuple(reasons))

        odds = context.pot_odds
        reasons.append(
            f"Pot odds: {context.to_call} betalen om {context.pot} te winnen → "
            f"je hebt minstens {odds:.0%} winkans nodig."
        )
        if equity >= 0.72 and context.legal.can_raise and self._chance(0.4 + profile.aggression * 0.5):
            reasons.append("Zeer sterke hand: raise voor waarde.")
            return Decision(self._bet_fraction_of_pot(context, 1.0), tuple(reasons))
        if equity >= odds + 0.04 * (1 - profile.looseness):
            reasons.append("Winkans is hoger dan de pot odds: call is winstgevend.")
            return Decision(Action(ActionType.CALL), tuple(reasons))
        if self._chance(profile.looseness * 0.15):
            reasons.append("Speculatieve call (losse speler).")
            return Decision(Action(ActionType.CALL), tuple(reasons))
        reasons.append("Winkans is lager dan de pot odds: fold.")
        return Decision(Action(ActionType.FOLD), tuple(reasons))


class Advisor(Protocol):
    def advise(self, context: DecisionContext) -> "Advice": ...


class HumanConsoleStrategy(DecisionStrategy):
    """Vraagt de mens om een actie; ``?`` toont het advies van de coach."""

    PROMPT = "Jouw actie ([h] voor hulp): "

    def __init__(self, io: UserIO, advisor: Advisor | None = None, auto_advice: bool = False) -> None:
        self._io = io
        self._advisor = advisor
        self.auto_advice = auto_advice

    def decide(self, context: DecisionContext) -> Action:
        self._io.show(self.render_situation(context))
        if self.auto_advice and self._advisor is not None:
            self._io.show(self._advisor.advise(context).text)
        while True:
            raw = self._io.ask(self.PROMPT).strip().lower()
            if raw == "q":
                raise QuitRequested()
            if raw == "?":
                if self._advisor is None:
                    self._io.show("Er is geen coach aan deze tafel.")
                else:
                    self._io.show(self._advisor.advise(context).text)
                continue
            if raw in ("h", "help", ""):
                self._io.show(self.render_options(context))
                continue
            action = self._parse(raw, context)
            if action is None:
                self._io.show("Dat begrijp ik niet. Typ [h] voor de mogelijke acties.")
                continue
            if action.type is ActionType.FOLD and context.legal.can_check:
                self._io.show("Tip: niemand heeft ingezet, dus je kunt gratis checken. Ik check voor je.")
                return Action(ActionType.CHECK)
            return action

    @staticmethod
    def _parse(raw: str, context: DecisionContext) -> Action | None:
        parts = raw.split()
        command, argument = parts[0], (parts[1] if len(parts) > 1 else None)
        if command in ("f", "fold"):
            return Action(ActionType.FOLD)
        if command in ("k", "check"):
            return Action(ActionType.CHECK)
        if command in ("c", "call"):
            return Action(ActionType.CALL) if context.to_call else Action(ActionType.CHECK)
        if command in ("a", "allin", "all-in"):
            return Action(ActionType.ALL_IN)
        if command in ("r", "b", "raise", "bet"):
            amount = int(argument) if argument and argument.isdigit() else context.legal.min_raise_to
            kind = ActionType.BET if context.current_bet == 0 else ActionType.RAISE
            return Action(kind, amount)
        if command.isdigit():
            kind = ActionType.BET if context.current_bet == 0 else ActionType.RAISE
            return Action(kind, int(command))
        return None

    @staticmethod
    def render_situation(context: DecisionContext) -> str:
        board = cards_to_str(context.board) if context.board else "(nog geen kaarten)"
        lines = [
            "",
            f"┌─ {context.street.upper()} ─ jouw beurt " + "─" * 40,
            f"│ Jouw kaarten: {cards_to_str(context.hole_cards)}    Board: {board}",
            f"│ Pot: {context.pot}    Te callen: {context.to_call}    Jouw stack: {context.stack}"
            f"    Positie: {context.position}",
        ]
        others = []
        for opponent in context.opponents:
            if opponent.folded:
                others.append(f"{opponent.name} (fold)")
            elif opponent.all_in:
                others.append(f"{opponent.name} ALL-IN {opponent.bet_this_street}")
            else:
                others.append(f"{opponent.name} {opponent.chips} [{opponent.bet_this_street}]")
        lines.append("│ Tegenstanders: " + " | ".join(others))
        lines.append("│ " + HumanConsoleStrategy.render_options(context))
        lines.append("└" + "─" * 58)
        return "\n".join(lines)

    @staticmethod
    def render_options(context: DecisionContext) -> str:
        legal = context.legal
        options = []
        if legal.can_check:
            options.append("[k] check")
        else:
            options.append("[f] fold")
            options.append(f"[c] call {legal.call_amount}")
        if legal.can_raise:
            verb = "bet" if context.current_bet == 0 else "raise naar"
            options.append(f"[r <bedrag>] {verb} (min {legal.min_raise_to}, max {legal.max_raise_to})")
        options.append(f"[a] all-in ({legal.max_raise_to})")
        options.append("[?] coach")
        options.append("[q] stoppen")
        return "  ".join(options)


class ScriptedStrategy(DecisionStrategy):
    """Speelt een vaste lijst acties af (voor tests)."""

    def __init__(self, actions: Sequence[Action]) -> None:
        self._actions = list(actions)
        self.contexts: list[DecisionContext] = []

    def decide(self, context: DecisionContext) -> Action:
        self.contexts.append(context)
        if not self._actions:
            return Action(ActionType.CHECK) if context.legal.can_check else Action(ActionType.FOLD)
        return self._actions.pop(0)
