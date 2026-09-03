"""Vertaalt spelgebeurtenissen naar JSON voor de browser.

Patroon: Observer. ``TablePresenter`` abonneert zich op de ``EventBus``, net als
``ConsoleView``, maar stuurt bij elke gebeurtenis ook een momentopname van de
tafel mee. Zo hoeft de browser geen spelregels te kennen: hij tekent gewoon
wat hij krijgt. Kaarten van bots blijven verborgen tot de showdown.
"""

from __future__ import annotations

from typing import Callable, Iterable, Mapping, Sequence

from ..actions import Action, ActionType
from ..cards import Card
from ..coach import Advice
from ..context import DecisionContext
from ..events import (
    BlindLevelChanged,
    CardBurned,
    CommunityCardsDealt,
    ForcedBetPosted,
    GameEvent,
    HandFinished,
    HandStarted,
    HoleCardsDealt,
    Message,
    PlayerActed,
    PlayerEliminated,
    PlayerThinking,
    PotAwarded,
    ShowdownReveal,
    TournamentFinished,
)
from ..players import Player
from ..tournament import BlindLevel

Emit = Callable[[dict], None]


# --- serialisatie ------------------------------------------------------------
def cards_json(cards: Iterable[Card]) -> list[str]:
    return [str(card) for card in cards]


def level_json(level: BlindLevel | None) -> dict | None:
    if level is None:
        return None
    return {
        "small_blind": level.small_blind,
        "big_blind": level.big_blind,
        "ante": level.ante,
        "text": str(level),
    }


def action_json(action: Action) -> dict:
    amount = f" {action.amount}" if action.amount and action.type in (ActionType.BET, ActionType.RAISE) else ""
    return {
        "type": action.type.value,
        "amount": action.amount,
        "text": str(action),
        "imperative": f"{action.type.imperative}{amount}",
    }


def advice_json(advice: Advice) -> dict:
    return {"lines": list(advice.lines), "action": action_json(advice.recommended)}


def decision_json(context: DecisionContext) -> dict:
    legal = context.legal
    return {
        "type": "decision",
        "street": context.street,
        "hole": cards_json(context.hole_cards),
        "board": cards_json(context.board),
        "pot": context.pot,
        "to_call": context.to_call,
        "stack": context.stack,
        "my_bet": context.player.bet_this_street,
        "current_bet": context.current_bet,
        "big_blind": context.big_blind,
        "position": context.position,
        "contenders": context.contenders,
        "pot_odds": round(context.pot_odds, 3),
        "legal": {
            "can_check": legal.can_check,
            "can_fold": legal.can_fold,
            "call_amount": legal.call_amount,
            "can_raise": legal.can_raise,
            "min_raise_to": legal.min_raise_to,
            "max_raise_to": legal.max_raise_to,
        },
        "opponents": [
            {
                "name": opponent.name,
                "chips": opponent.chips,
                "bet": opponent.bet_this_street,
                "folded": opponent.folded,
                "all_in": opponent.all_in,
                "position": opponent.position,
            }
            for opponent in context.opponents
        ],
    }


# --- de presenter ------------------------------------------------------------
class TablePresenter:
    def __init__(self, emit: Emit, seats: Sequence[Player], human_name: str, styles: Mapping[str, str]) -> None:
        self._emit = emit
        self._seats = list(seats)
        self._human_name = human_name
        self._styles = dict(styles)
        self._hand_number = 0
        self._level: BlindLevel | None = None
        self._level_number = 0
        self._street = "preflop"
        self._board: list[str] = []
        self._pot = 0
        self._button: str | None = None
        self._in_hand: set[str] = set()
        self._human_cards: list[str] = []
        self._revealed: dict[str, list[str]] = {}
        self._hands: dict[str, dict] = {}

    # --- momentopname -------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "hand_number": self._hand_number,
            "level": level_json(self._level),
            "level_number": self._level_number,
            "street": self._street,
            "board": list(self._board),
            "pot": self._pot,
            "button": self._button,
            "seats": [self._seat_json(player) for player in self._seats],
        }

    def _seat_json(self, player: Player) -> dict:
        name = player.name
        in_hand = name in self._in_hand
        if name == self._human_name:
            cards: list[str] | None = list(self._human_cards) if in_hand and self._human_cards else None
        else:
            cards = self._revealed.get(name)
        return {
            "name": name,
            "chips": player.chips,
            "bet": player.bet_this_street,
            "folded": player.folded,
            "all_in": player.all_in,
            "is_human": player.is_human,
            "in_hand": in_hand,
            "is_button": name == self._button,
            "out": player.chips == 0 and not in_hand,
            "cards": cards,
            "hand": self._hands.get(name),
            "style": self._styles.get(name),
        }

    # --- observer -----------------------------------------------------------
    def notify(self, event: GameEvent) -> None:
        payload = self._translate(event)
        if payload is None:
            return
        payload["state"] = self.snapshot()
        self._emit(payload)

    def _translate(self, event: GameEvent) -> dict | None:
        if isinstance(event, HandStarted):
            return self._hand_started(event)
        if isinstance(event, ForcedBetPosted):
            self._pot += event.amount
            return {
                "type": "forced_bet",
                "player": event.player.name,
                "kind": event.kind,
                "amount": event.amount,
                "text": f"{event.player.name} zet {event.kind} {event.amount}",
            }
        if isinstance(event, HoleCardsDealt):
            if event.player.name != self._human_name:
                return None
            self._human_cards = cards_json(event.cards)
            return {
                "type": "hole_cards",
                "cards": list(self._human_cards),
                "text": "Jouw kaarten: " + " ".join(self._human_cards),
            }
        if isinstance(event, CardBurned):
            return {"type": "burn", "street": event.street, "text": f"De dealer legt een burn card weg ({event.street})."}
        if isinstance(event, CommunityCardsDealt):
            self._street = event.street
            self._board = cards_json(event.board)
            self._pot = event.pot
            return {
                "type": "community",
                "street": event.street,
                "new_cards": cards_json(event.new_cards),
                "board": list(self._board),
                "pot": event.pot,
                "text": f"{event.street.upper()}: " + " ".join(self._board) + f"  (pot {event.pot})",
            }
        if isinstance(event, PlayerThinking):
            return {"type": "thinking", "player": event.player.name}
        if isinstance(event, PlayerActed):
            self._pot = event.pot
            return {
                "type": "action",
                "player": event.player.name,
                "action": action_json(event.action),
                "street": event.street,
                "pot": event.pot,
                "text": f"{event.player.name} {event.action}  (pot {event.pot})",
            }
        if isinstance(event, ShowdownReveal):
            return self._showdown(event)
        if isinstance(event, PotAwarded):
            self._pot = max(0, self._pot - event.amount)
            detail = f" met {event.hand.describe()}" if event.hand else ""
            return {
                "type": "pot_awarded",
                "player": event.player.name,
                "amount": event.amount,
                "reason": event.reason,
                "hand": event.hand.describe() if event.hand else None,
                "text": f"{event.player.name} wint {event.amount} ({event.reason}){detail}",
            }
        if isinstance(event, HandFinished):
            return {"type": "hand_finished", "hand_number": event.hand_number}
        if isinstance(event, PlayerEliminated):
            return {
                "type": "eliminated",
                "player": event.player.name,
                "place": event.finishing_place,
                "text": f"{event.player.name} is uitgeschakeld op plaats {event.finishing_place}.",
            }
        if isinstance(event, BlindLevelChanged):
            self._level = event.level
            self._level_number = event.level_number
            return {
                "type": "level",
                "level": level_json(event.level),
                "number": event.level_number,
                "text": f"Niveau {event.level_number}: blinds {event.level}",
            }
        if isinstance(event, TournamentFinished):
            return {
                "type": "tournament_finished",
                "winner": event.winner.name,
                "ranking": [p.name for p in event.ranking],
                "text": f"{event.winner.name} wint het toernooi!",
            }
        if isinstance(event, Message):
            return {"type": "message", "text": event.text}
        return None

    def _hand_started(self, event: HandStarted) -> dict:
        self._hand_number = event.hand_number
        self._level = event.level
        self._street = "preflop"
        self._board = []
        self._pot = 0
        self._button = event.button.name
        self._in_hand = {p.name for p in event.players}
        self._human_cards = []
        self._revealed = {}
        self._hands = {}
        return {
            "type": "hand_started",
            "hand_number": event.hand_number,
            "button": event.button.name,
            "level": level_json(event.level),
            "players": [p.name for p in event.players],
            "text": f"Hand {event.hand_number} - blinds {event.level} - button: {event.button.name}",
        }

    def _showdown(self, event: ShowdownReveal) -> dict:
        cards = cards_json(event.cards)
        hand = {"text": event.hand.describe(), "best_five": cards_json(event.hand.best_five)}
        if event.player.name != self._human_name:
            self._revealed[event.player.name] = cards
        self._hands[event.player.name] = hand
        return {
            "type": "showdown",
            "player": event.player.name,
            "cards": cards,
            "hand": hand,
            "text": f"Showdown: {event.player.name} toont " + " ".join(cards) + f" - {event.hand.describe()}",
        }
