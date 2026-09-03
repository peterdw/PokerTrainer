"""Waarnemers die het spelverloop tonen of bijhouden (Observer)."""

from __future__ import annotations

from .cards import cards_to_str
from .console import UserIO
from .events import (
    BlindLevelChanged,
    CommunityCardsDealt,
    ForcedBetPosted,
    GameEvent,
    HandFinished,
    HandStarted,
    HoleCardsDealt,
    Message,
    PlayerActed,
    PlayerEliminated,
    PotAwarded,
    ShowdownReveal,
    TournamentFinished,
)


class ConsoleView:
    """Vertaalt gebeurtenissen naar tekst. Verbergt de kaarten van de bots."""

    def __init__(self, io: UserIO, human_name: str | None = None, verbose: bool = True) -> None:
        self._io = io
        self._human_name = human_name
        self._verbose = verbose

    def notify(self, event: GameEvent) -> None:
        if isinstance(event, HandStarted):
            self._io.show("")
            self._io.show(f"═══ Hand {event.hand_number} ═══ blinds {event.level} ═══ button: {event.button.name}")
            stacks = "  ".join(f"{p.name}: {p.chips}" for p in event.players)
            self._io.show(f"Stacks: {stacks}")
        elif isinstance(event, ForcedBetPosted):
            self._io.show(f"  {event.player.name} zet {event.kind} {event.amount}")
        elif isinstance(event, HoleCardsDealt):
            if event.player.name == self._human_name:
                self._io.show(f"  Jouw kaarten: {cards_to_str(event.cards)}")
        elif isinstance(event, CommunityCardsDealt):
            self._io.show(f"--- {event.street.upper()}: {cards_to_str(event.board)}   (pot {event.pot})")
        elif isinstance(event, PlayerActed):
            if self._verbose or event.player.name != self._human_name:
                self._io.show(f"  {event.player.name} {event.action}   (pot {event.pot})")
        elif isinstance(event, ShowdownReveal):
            self._io.show(f"  Showdown: {event.player.name} toont {cards_to_str(event.cards)} → {event.hand.describe()}")
        elif isinstance(event, PotAwarded):
            detail = f" met {event.hand.describe()}" if event.hand else ""
            self._io.show(f"  ➜ {event.player.name} wint {event.amount} ({event.reason}){detail}")
        elif isinstance(event, PlayerEliminated):
            self._io.show(f"  ✗ {event.player.name} is uitgeschakeld op plaats {event.finishing_place}.")
        elif isinstance(event, BlindLevelChanged):
            self._io.show("")
            self._io.show(f"▲▲ Niveau {event.level_number}: blinds {event.level} ▲▲")
        elif isinstance(event, TournamentFinished):
            self._io.show("")
            self._io.show(f"🏆 {event.winner.name} wint het toernooi!")
        elif isinstance(event, Message):
            self._io.show(f"  ! {event.text}")
        elif isinstance(event, HandFinished):
            pass


class SessionStats:
    """Houdt bij hoe de mens het doet."""

    def __init__(self, human_name: str) -> None:
        self._human_name = human_name
        self.hands = 0
        self.hands_won = 0
        self.showdowns_seen = 0
        self.chips_won = 0
        self.folded_preflop = 0
        self._won_this_hand = False

    def notify(self, event: GameEvent) -> None:
        if isinstance(event, HandStarted):
            self.hands += 1
            self._won_this_hand = False
        elif isinstance(event, PlayerActed) and event.player.name == self._human_name:
            if event.player.folded and event.street == "preflop":
                self.folded_preflop += 1
        elif isinstance(event, ShowdownReveal) and event.player.name == self._human_name:
            self.showdowns_seen += 1
        elif isinstance(event, PotAwarded) and event.player.name == self._human_name:
            self.chips_won += event.amount
            if not self._won_this_hand and event.reason != "ongecalld deel terug":
                self._won_this_hand = True
                self.hands_won += 1

    def summary(self) -> str:
        if self.hands == 0:
            return "Je hebt nog geen handen gespeeld."
        return (
            f"Handen gespeeld: {self.hands} | gewonnen: {self.hands_won} | "
            f"preflop gefold: {self.folded_preflop} | showdowns: {self.showdowns_seen}"
        )
