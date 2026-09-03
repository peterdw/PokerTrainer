"""Adapters tussen de spelmotor en de browser.

Patronen:
- Adapter: ``WebIO`` en ``WebHumanStrategy`` vervullen de bestaande contracten
  (``UserIO`` en ``DecisionStrategy``), maar praten met een gebeurtenissenstroom
  en een postvak in plaats van met ``print``/``input``.
- Decorator: ``PacedStrategy`` omhult een botstrategie met bedenktijd, zodat het
  spel in de browser te volgen is. De bot zelf verandert niet.
- Observer: ``PacingObserver`` last korte pauzes in na kaarten en potuitkering.
"""

from __future__ import annotations

import queue
import random
import threading
from typing import Callable, Mapping

from ..actions import Action, ActionType
from ..console import QuitRequested
from ..context import DecisionContext
from ..events import (
    BlindLevelChanged,
    CardBurned,
    CommunityCardsDealt,
    EventBus,
    ForcedBetPosted,
    GameEvent,
    HandFinished,
    HandStarted,
    HoleCardsDealt,
    PlayerEliminated,
    PlayerThinking,
    PotAwarded,
    ShowdownReveal,
)
from ..strategies import Advisor, DecisionStrategy
from .presenter import advice_json, decision_json

Emit = Callable[[dict], None]


class Tempo:
    """Bepaalt hoe lang pauzes duren en maakt ze onderbreekbaar.

    ``factor`` 1.0 = normaal tempo, 0.0 = geen pauzes (tests). ``stop()`` breekt
    elke lopende of toekomstige pauze af met ``QuitRequested``.
    """

    def __init__(self, factor: float = 1.0) -> None:
        self.factor = factor
        self._stopped = threading.Event()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def stop(self) -> None:
        self._stopped.set()

    def pause(self, seconds: float) -> None:
        if self._stopped.wait(seconds * self.factor):
            raise QuitRequested()


class WebIO:
    """``UserIO`` die tekst als gebeurtenis doorgeeft; de Coach gebruikt dit
    voor zijn commentaar op het board."""

    def __init__(self, emit: Emit, channel: str = "coach") -> None:
        self._emit = emit
        self._channel = channel

    def show(self, text: str = "") -> None:
        text = text.strip().removeprefix("🎓").strip()
        if text:
            self._emit({"type": self._channel, "text": text})

    def ask(self, prompt: str) -> str:
        raise RuntimeError("De browserversie stelt geen vrije tekstvragen.")


class WebHumanStrategy(DecisionStrategy):
    """Stuurt de beslissituatie naar de browser en wacht op het antwoord."""

    def __init__(self, emit: Emit, inbox: "queue.Queue[dict | None]", advisor: Advisor | None, auto_advice: bool) -> None:
        self._emit = emit
        self._inbox = inbox
        self._advisor = advisor
        self._auto_advice = auto_advice
        self.pending: DecisionContext | None = None

    def decide(self, context: DecisionContext) -> Action:
        self.pending = context
        payload = decision_json(context)
        if self._auto_advice and self._advisor is not None:
            payload["advice"] = advice_json(self._advisor.advise(context))
        self._emit(payload)
        try:
            while True:
                answer = self._inbox.get()
                if answer is None:
                    raise QuitRequested()
                action = self.parse(answer, context)
                if action is None:
                    self._emit({"type": "message", "text": "Die actie ken ik niet."})
                    continue
                if action.type is ActionType.FOLD and context.legal.can_check:
                    self._emit({"type": "message", "text": "Niemand heeft ingezet, dus je checkt gratis."})
                    return Action(ActionType.CHECK)
                return action
        finally:
            self.pending = None

    def advise(self) -> dict | None:
        """Advies van de coach voor de beslissing die nu openstaat."""
        if self.pending is None or self._advisor is None:
            return None
        return advice_json(self._advisor.advise(self.pending))

    @staticmethod
    def parse(answer: Mapping[str, object], context: DecisionContext) -> Action | None:
        kind = str(answer.get("type", "")).lower()
        raw_amount = answer.get("amount", 0)
        amount = int(raw_amount) if isinstance(raw_amount, (int, float, str)) and str(raw_amount).isdigit() else 0
        if kind == "fold":
            return Action(ActionType.FOLD)
        if kind == "check":
            return Action(ActionType.CHECK)
        if kind == "call":
            return Action(ActionType.CALL) if context.to_call else Action(ActionType.CHECK)
        if kind in ("all-in", "allin"):
            return Action(ActionType.ALL_IN)
        if kind in ("raise", "bet"):
            target = amount or context.legal.min_raise_to
            variant = ActionType.BET if context.current_bet == 0 else ActionType.RAISE
            return Action(variant, target)
        return None


class PacedStrategy(DecisionStrategy):
    """Decorator: kondigt aan dat de bot nadenkt en wacht even voor hij beslist."""

    def __init__(self, inner: DecisionStrategy, tempo: Tempo, bus: EventBus, rng: random.Random) -> None:
        self._inner = inner
        self._tempo = tempo
        self._bus = bus
        self._rng = rng

    def decide(self, context: DecisionContext) -> Action:
        self._bus.publish(PlayerThinking(context.player))
        self._tempo.pause(self._rng.uniform(0.6, 1.4))
        return self._inner.decide(context)


class PacingObserver:
    """Pauzeert na gebeurtenissen die de kijker even moet kunnen opnemen.

    Abonneer deze waarnemer ná de presenter, zodat de browser de gebeurtenis
    al heeft ontvangen voordat de pauze begint.
    """

    PAUSES: dict[type, float] = {
        HandStarted: 1.7,  # tijd om de kaarten rond te delen
        CardBurned: 0.55,
        ForcedBetPosted: 0.25,
        HoleCardsDealt: 0.15,
        CommunityCardsDealt: 1.2,
        ShowdownReveal: 0.9,
        PotAwarded: 1.3,
        HandFinished: 1.4,
        BlindLevelChanged: 1.0,
        PlayerEliminated: 1.0,
    }

    def __init__(self, tempo: Tempo) -> None:
        self._tempo = tempo

    def notify(self, event: GameEvent) -> None:
        seconds = self.PAUSES.get(type(event))
        if seconds:
            self._tempo.pause(seconds)
