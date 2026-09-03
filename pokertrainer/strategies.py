"""Beslisstrategieën.

Patroon: Strategy. Een ``Player`` heeft een ``DecisionStrategy``; de spelmotor
vraagt alleen ``decide(context)`` en weet niet of er een mens, een tight bot of
een maniak achter zit. Bots geven bovendien hun redenering terug, zodat de
coach dezelfde logica kan gebruiken om uit te leggen waarom iets een goede zet is.
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Sequence

from .actions import Action, ActionType
from .cards import Card, Rank, cards_to_str
from .console import QuitRequested, UserIO
from .context import DecisionContext
from .equity import EquityCalculator
from .evaluation import HandEvaluator

if TYPE_CHECKING:
    from .coach import Advice


@dataclass(frozen=True)
class Decision:
    action: Action
    reasons: tuple[str, ...]


class DecisionStrategy(ABC):
    @abstractmethod
    def decide(self, context: DecisionContext) -> Action: ...


# --- starthanden ------------------------------------------------------------
def hand_label(cards: Sequence[Card]) -> str:
    """``A♠ K♠`` -> ``AKs``, ``T♥ 9♦`` -> ``T9o``, ``Q♣ Q♦`` -> ``QQ``."""
    high, low = sorted(cards, reverse=True)
    if high.rank == low.rank:
        return f"{high.rank.label}{low.rank.label}"
    suffix = "s" if high.suit == low.suit else "o"
    return f"{high.rank.label}{low.rank.label}{suffix}"


def chen_breakdown(cards: Sequence[Card]) -> list[tuple[str, float]]:
    """De onderdelen van de Chen-formule: (omschrijving, punten). Som + afronden naar boven = score."""
    high, low = sorted(cards, reverse=True)
    base = {Rank.ACE: 10.0, Rank.KING: 8.0, Rank.QUEEN: 7.0, Rank.JACK: 6.0}.get(high.rank, high.rank.value / 2)
    parts = [(f"hoogste kaart {high.rank.dutch_name}", base)]
    if high.rank == low.rank:
        parts.append(("paar: punten verdubbeld (minimaal 5)", max(5.0, base * 2) - base))
        return parts
    if high.suit == low.suit:
        parts.append(("suited", 2.0))
    gap = high.rank.value - low.rank.value - 1
    penalty = {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
    if penalty:
        parts.append((f"gat van {gap} kaart{'en' if gap > 1 else ''}", -float(penalty)))
    if gap <= 1 and high.rank.value < Rank.QUEEN.value:
        parts.append(("aansluitend onder de vrouw", 1.0))
    return parts


def chen_score(cards: Sequence[Card]) -> int:
    """Chen-formule: een klassieke score (ongeveer -1 .. 20) voor starthanden."""
    return math.ceil(sum(points for _, points in chen_breakdown(cards)))


def chen_explanation(cards: Sequence[Card]) -> str:
    """``"hoogste kaart heer 8, gat van 7 kaarten -5 = 3"``"""

    def number(points: float, signed: bool) -> str:
        text = f"{points:g}".replace(".", ",")
        return f"+{text}" if signed and points > 0 else text

    parts = chen_breakdown(cards)
    pieces = [f"{label} {number(points, index > 0)}" for index, (label, points) in enumerate(parts)]
    return ", ".join(pieces) + f" = {chen_score(cards)}"


def starting_hand_class(score: int) -> str:
    if score >= 12:
        return "premium"
    if score >= 9:
        return "sterk"
    if score >= 7:
        return "speelbaar"
    if score >= 5:
        return "marginaal"
    return "zwak"


@dataclass(frozen=True)
class BotProfile:
    key: str
    name: str
    looseness: float  # 0 = speelt bijna niets, 1 = speelt alles
    aggression: float  # 0 = callt liever, 1 = bet en raiset graag
    description: str


class HeuristicBotStrategy(DecisionStrategy):
    """Speelt op basis van starthandscore (preflop) en winkans vs pot odds (postflop)."""

    def __init__(
        self,
        profile: BotProfile,
        evaluator: HandEvaluator,
        equity: EquityCalculator,
        rng: random.Random | None = None,
        mix: bool = True,
    ) -> None:
        self._profile = profile
        self._evaluator = evaluator
        self._equity = equity
        self._rng = rng or random.Random()
        self._mix = mix  # False = deterministisch (gebruikt door de coach)

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
        profile = self._profile
        label = hand_label(context.hole_cards)
        score = chen_score(context.hole_cards)
        reasons = [f"Starthand {label}: Chen-score {score}/20 ({starting_hand_class(score)})."]
        late = context.position.startswith(("button", "cutoff"))
        if late:
            score += 1
            reasons.append("Late positie: je mag iets meer handen spelen (+1).")
        open_threshold = 9 - 4 * profile.looseness
        premium = 11
        facing_raise = context.current_bet > context.big_blind
        bb = context.big_blind

        if context.stack_in_big_blinds <= 10 and score >= open_threshold:
            reasons.append("Korte stack (≤ 10 big blinds): speel push-or-fold; all-in met een speelbare hand.")
            return Decision(Action(ActionType.ALL_IN), tuple(reasons))

        if not facing_raise:
            callers = sum(1 for o in context.opponents if o.bet_this_street >= bb and o.position != "big blind")
            if score >= premium or (score >= open_threshold and self._chance(0.4 + profile.aggression / 2)):
                reasons.append("Niemand heeft geraised: open met een raise van ± 3 big blinds (+1 per limper).")
                return Decision(self._raise_to(context, (3 + callers) * bb), tuple(reasons))
            if score >= open_threshold:
                reasons.append("Speelbare hand, maar niet sterk genoeg om te raisen: meedoen voor de big blind.")
                return Decision(self._call_or_check(context), tuple(reasons))
            if context.legal.can_check:
                reasons.append("Zwakke hand, maar je mag gratis de flop zien: check.")
                return Decision(Action(ActionType.CHECK), tuple(reasons))
            reasons.append("Te zwak om chips in te zetten: fold.")
            return Decision(Action(ActionType.FOLD), tuple(reasons))

        reasons.append(f"Er ligt een raise naar {context.current_bet}; je moet {context.to_call} bijleggen.")
        if score >= premium:
            if context.legal.can_raise and self._chance(0.3 + profile.aggression * 0.6):
                reasons.append("Premium hand: re-raise (3-bet) naar ± 3x de raise om de pot te bouwen.")
                return Decision(self._raise_to(context, 3 * context.current_bet), tuple(reasons))
            reasons.append("Premium hand: minstens callen.")
            return Decision(self._call_or_check(context), tuple(reasons))
        cheap = context.to_call <= max(3 * bb, int(0.12 * context.stack))
        if score >= open_threshold + 2 and cheap:
            reasons.append("Goede hand en de call is relatief goedkoop: call en kijk naar de flop.")
            return Decision(self._call_or_check(context), tuple(reasons))
        if context.legal.can_check:
            return Decision(Action(ActionType.CHECK), tuple(reasons))
        reasons.append("Niet sterk genoeg om een raise te betalen: fold (chips bewaren voor betere spots).")
        return Decision(Action(ActionType.FOLD), tuple(reasons))

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
