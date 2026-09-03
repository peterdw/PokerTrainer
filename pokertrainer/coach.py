"""De coach: legt uit wat er aan de hand is en geeft een onderbouwd advies.

De coach is tegelijk een Observer (hij becommentarieert het board zodra er
kaarten komen) en een adviseur die, op verzoek of automatisch, de redenering
van een solide strategie in mensentaal vertaalt.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .actions import Action, ActionType
from .cards import Card, Rank, Suit
from .console import UserIO
from .context import DecisionContext
from .equity import EquityCalculator
from .evaluation import HandCategory, HandEvaluator
from .events import CommunityCardsDealt, GameEvent, HandStarted, HoleCardsDealt, PlayerActed
from .strategies import BotProfile, HeuristicBotStrategy, chen_score, hand_label, starting_hand_class

COACH_PROFILE = BotProfile("coach", "Coach", 0.45, 0.6, "solide, uitgebalanceerd")


@dataclass(frozen=True)
class Advice:
    lines: tuple[str, ...]
    recommended: Action

    @property
    def text(self) -> str:
        return "\n".join(f"  🎓 {line}" for line in self.lines)


POSITION_TIPS = {
    "button": "de button handelt na de flop altijd als laatste: het grootste voordeel aan tafel.",
    "button (small blind)": "heads-up ben je button én small blind: preflop als eerste, daarna als laatste.",
    "cutoff (laat)": "laat: bijna altijd als laatste aan de beurt, goede plek om te raisen.",
    "midden": "midden: gemiddeld; speel iets selectiever dan op de button.",
    "vroeg (under the gun)": "vroeg: veel spelers na jou, speel alleen sterke handen.",
    "small blind": "small blind: na de flop moet jij als eerste handelen, dat is een nadeel.",
    "big blind": "big blind: je hebt al geld in de pot; preflop mag je vaak goedkoop meedoen.",
}


def flush_draw(cards: Sequence[Card]) -> Suit | None:
    counts = Counter(card.suit for card in cards)
    for suit, count in counts.items():
        if count == 4:
            return suit
    return None


def straight_outs(cards: Sequence[Card]) -> int:
    """Aantal kaartwaarden die een straight zouden maken (0, 1 = gutshot, 2 = open-ended)."""
    ranks = {card.rank.value for card in cards}
    if len(ranks) < 4:
        return 0
    from .evaluation import _straight_high  # bewust hergebruik van de officiële logica

    if _straight_high(ranks) is not None:
        return 0
    outs = 0
    for candidate in range(2, 15):
        if candidate in ranks:
            continue
        if _straight_high(ranks | {candidate}) is not None:
            outs += 1
    return outs


class Coach:
    def __init__(
        self,
        evaluator: HandEvaluator,
        equity: EquityCalculator,
        io: UserIO,
        human_name: str,
        rng: random.Random | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._io = io
        self._human_name = human_name
        self._strategy = HeuristicBotStrategy(COACH_PROFILE, evaluator, equity, rng, mix=False)
        self._human_cards: tuple[Card, ...] = ()
        self._human_in_hand = False
        self.board_comments = True

    # --- adviseur -----------------------------------------------------------
    def advise(self, context: DecisionContext) -> Advice:
        lines: list[str] = []
        if context.street == "preflop":
            lines.extend(self._preflop_lines(context))
        else:
            lines.extend(self._draw_lines(context))
        tip = POSITION_TIPS.get(context.position)
        if tip:
            lines.append(f"Positie: {tip}")
        decision = self._strategy.reason(context)
        lines.extend(decision.reasons)
        action = decision.action
        amount = f" {action.amount}" if action.amount and action.type in (ActionType.BET, ActionType.RAISE) else ""
        lines.append(f"ADVIES: {action.type.imperative}{amount}")
        return Advice(tuple(lines), action)

    @staticmethod
    def _preflop_lines(context: DecisionContext) -> list[str]:
        label = hand_label(context.hole_cards)
        score = chen_score(context.hole_cards)
        lines = [f"Je starthand is {label} (klasse: {starting_hand_class(score)})."]
        high, low = sorted(context.hole_cards, reverse=True)
        if high.rank == low.rank:
            lines.append("Een pocket pair: je hebt al een paar; hoe hoger, hoe beter.")
        elif high.suit == low.suit:
            lines.append("Suited: iets meer kans op een flush (ongeveer +2-3% winkans).")
        if high.rank >= Rank.TEN and low.rank >= Rank.TEN:
            lines.append("Twee hoge kaarten (broadways): goed voor sterke paren en straights.")
        return lines

    def _draw_lines(self, context: DecisionContext) -> list[str]:
        cards = [*context.hole_cards, *context.board]
        lines: list[str] = []
        if context.street == "river":
            return lines
        suit = flush_draw(cards)
        if suit is not None:
            lines.append(f"Flush draw in {suit.dutch_name}: 9 outs (± {'35' if context.street == 'flop' else '19'}% kans).")
        outs = straight_outs(cards)
        if outs >= 2:
            lines.append("Open-ended straight draw: 8 outs (± 32% op de flop, 17% op de turn).")
        elif outs == 1:
            lines.append("Gutshot straight draw: 4 outs (± 17% op de flop, 9% op de turn).")
        if lines:
            lines.append("Vuistregel: outs × 4 (flop) of outs × 2 (turn) ≈ kans in procent.")
        return lines

    # --- observer -----------------------------------------------------------
    def notify(self, event: GameEvent) -> None:
        if isinstance(event, HandStarted):
            self._human_in_hand = any(p.name == self._human_name for p in event.players)
            self._human_cards = ()
        elif isinstance(event, HoleCardsDealt) and event.player.name == self._human_name:
            self._human_cards = tuple(event.cards)
        elif isinstance(event, PlayerActed) and event.player.name == self._human_name and event.player.folded:
            self._human_in_hand = False
        elif isinstance(event, CommunityCardsDealt) and self._human_in_hand and self.board_comments:
            for line in self._board_texture(event.board, event.new_cards):
                self._io.show(f"  🎓 {line}")

    def _board_texture(self, board: Sequence[Card], new_cards: Sequence[Card]) -> list[str]:
        lines: list[str] = []
        suits = Counter(card.suit for card in board)
        ranks = Counter(card.rank for card in board)
        top_suit, suit_count = suits.most_common(1)[0]
        if suit_count >= 3:
            lines.append(f"Drie of meer {top_suit.dutch_name} op tafel: een flush is mogelijk.")
        elif suit_count == 2 and len(board) == 3:
            lines.append(f"Twee {top_suit.dutch_name} op de flop: tegenstanders kunnen een flush draw hebben.")
        if any(count >= 2 for count in ranks.values()):
            lines.append("Gepaard board: full house en carré zijn mogelijk; wees voorzichtig met alleen een paar.")
        if self._human_cards:
            value = self._evaluator.best_hand(self._human_cards, board)
            if value.category >= HandCategory.TWO_PAIR:
                lines.append(f"Jij hebt nu: {value.describe()}.")
            elif value.category is HandCategory.ONE_PAIR:
                pair_rank = value.kickers[0]
                board_high = max(card.rank.value for card in board)
                if pair_rank >= board_high:
                    lines.append("Je hebt top pair (of beter): een sterke hand op dit board.")
        return lines
