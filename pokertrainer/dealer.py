"""De dealer speelt één hand van begin tot eind: blinds, kaarten, inzetrondes,
showdown en het verdelen van (zij)potten."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .actions import LegalActions
from .betting import BettingRound
from .cards import Deck
from .context import DecisionContext, OpponentInfo
from .evaluation import HandEvaluator, HandValue
from .events import (
    EventBus,
    ForcedBetPosted,
    HandFinished,
    HandStarted,
    PotAwarded,
    ShowdownReveal,
)
from .players import Player
from .streets import HandContext, PreFlop, Street
from .table import Table
from .tournament import BlindLevel


@dataclass
class Pot:
    amount: int
    eligible: list[Player]


class PotCalculator:
    """Verdeelt de totale inzet in hoofdpot en zijpotten op basis van wat elke
    speler in totaal heeft ingezet (de officiële methode)."""

    @staticmethod
    def split(players: list[Player]) -> list[Pot]:
        levels = sorted({p.invested_this_hand for p in players if p.invested_this_hand > 0})
        pots: list[Pot] = []
        floor = 0
        for level in levels:
            amount = sum(min(p.invested_this_hand, level) - floor for p in players if p.invested_this_hand > floor)
            eligible = [p for p in players if p.is_contender and p.invested_this_hand >= level]
            if not eligible and pots:
                pots[-1].amount += amount
            elif pots and pots[-1].eligible == eligible:
                pots[-1].amount += amount
            else:
                pots.append(Pot(amount, eligible))
            floor = level
        return pots


class HandRunner:
    def __init__(
        self,
        table: Table,
        bus: EventBus,
        evaluator: HandEvaluator,
        rng: random.Random | None = None,
        big_blind_ante: bool = True,
    ) -> None:
        self._table = table
        self._bus = bus
        self._evaluator = evaluator
        self._rng = rng or random.Random()
        self._big_blind_ante = big_blind_ante
        self._last_aggressor: Player | None = None

    # --- publieke API -------------------------------------------------------
    def play_hand(self, hand_number: int, level: BlindLevel) -> None:
        seated = [p for p in self._table.clockwise_from(self._table.button, lambda p: p.chips > 0)]
        for player in seated:
            player.reset_for_hand()
        button = seated[0]
        small_blind = button if len(seated) == 2 else seated[1]
        players = Table.rotate_from(seated, small_blind)
        big_blind = players[1]
        self._last_aggressor = None
        self._bus.publish(HandStarted(hand_number, button, level, tuple(players)))

        self._post_forced_bets(players, small_blind, big_blind, level)
        hand = HandContext(Deck(self._rng), players, self._bus)

        street: Street | None = PreFlop()
        while street is not None:
            street.deal(hand)
            if street.has_betting:
                self._run_betting(hand, street, button, big_blind, level)
                for player in players:
                    player.reset_for_street()
            if len(hand.contenders) == 1:
                break
            street = street.next()

        self._settle(hand, button)
        self._bus.publish(HandFinished(hand_number, tuple(players)))

    # --- onderdelen ---------------------------------------------------------
    def _post_forced_bets(self, players: list[Player], sb: Player, bb: Player, level: BlindLevel) -> None:
        if level.ante:
            payers = [bb] if self._big_blind_ante else players
            for player in payers:
                paid = player.post_ante(level.ante)
                self._bus.publish(ForcedBetPosted(player, "ante", paid))
        self._bus.publish(ForcedBetPosted(sb, "small blind", sb.commit(level.small_blind)))
        self._bus.publish(ForcedBetPosted(bb, "big blind", bb.commit(level.big_blind)))

    def _run_betting(self, hand: HandContext, street: Street, button: Player, bb: Player, level: BlindLevel) -> None:
        if street.name == "preflop":
            order = Table.rotate_after(hand.players, bb)
            opening_bet = level.big_blind
        else:
            order = Table.rotate_after(hand.players, button)
            opening_bet = 0

        def context_factory(player: Player, legal: LegalActions) -> DecisionContext:
            return self._build_context(hand, street, button, player, legal, level, betting_round.current_bet)

        betting_round = BettingRound(
            order, level.big_blind, self._bus, street.name, context_factory, lambda: hand.pot, opening_bet
        )
        betting_round.run()
        if betting_round.last_aggressor is not None:
            self._last_aggressor = betting_round.last_aggressor

    def _build_context(
        self,
        hand: HandContext,
        street: Street,
        button: Player,
        player: Player,
        legal: LegalActions,
        level: BlindLevel,
        current_bet: int,
    ) -> DecisionContext:
        positions = self._positions(hand.players, button)
        to_act_after = 0
        if player is not button:  # de button handelt postflop als laatste
            for other in Table.rotate_after(hand.players, player):
                if other.can_act:
                    to_act_after += 1
                if other is button:
                    break
        opponents = tuple(
            OpponentInfo(p.name, p.chips, p.bet_this_street, p.folded, p.all_in, positions[p])
            for p in hand.players
            if p is not player
        )
        return DecisionContext(
            player=player,
            hole_cards=tuple(player.hole_cards),
            board=tuple(hand.board),
            street=street.name,
            pot=hand.pot,
            current_bet=current_bet,
            legal=legal,
            big_blind=level.big_blind,
            position=positions[player],
            players_to_act_after=to_act_after,
            contenders=len(hand.contenders),
            opponents=opponents,
        )

    @staticmethod
    def _positions(players: list[Player], button: Player) -> dict[Player, str]:
        names: dict[Player, str] = {}
        count = len(players)
        for index, player in enumerate(players):
            if count == 2:
                names[player] = "button (small blind)" if player is button else "big blind"
                continue
            distance_to_button = count - 1 - index
            if index == 0:
                names[player] = "small blind"
            elif index == 1:
                names[player] = "big blind"
            elif distance_to_button == 0:
                names[player] = "button"
            elif distance_to_button == 1:
                names[player] = "cutoff (laat)"
            elif distance_to_button <= 3:
                names[player] = "midden"
            else:
                names[player] = "vroeg (under the gun)"
        return names

    def _settle(self, hand: HandContext, button: Player) -> None:
        pots = PotCalculator.split(hand.players)
        contenders = hand.contenders
        if len(contenders) == 1:
            winner = contenders[0]
            total = sum(pot.amount for pot in pots)
            winner.receive(total)
            self._bus.publish(PotAwarded(winner, total, "iedereen paste"))
            return

        values = {p: self._evaluator.best_hand(p.hole_cards, hand.board) for p in contenders}
        for player in self._showdown_order(hand.players, button):
            if player.is_contender:
                self._bus.publish(ShowdownReveal(player, tuple(player.hole_cards), values[player]))

        after_button = Table.rotate_after(hand.players, button)
        for index, pot in enumerate(pots):
            label = "hoofdpot" if index == 0 else f"zijpot {index}"
            if len(pot.eligible) == 1:
                only = pot.eligible[0]
                only.receive(pot.amount)
                self._bus.publish(PotAwarded(only, pot.amount, "ongecalld deel terug"))
                continue
            best = max(values[p] for p in pot.eligible)
            winners = [p for p in after_button if p in pot.eligible and values[p] == best]
            share, remainder = divmod(pot.amount, len(winners))
            for winner in winners:  # oneven chip gaat naar de eerste speler links van de button
                extra = 1 if remainder > 0 else 0
                remainder -= extra
                winner.receive(share + extra)
                reason = label if len(winners) == 1 else f"{label}, gedeeld"
                self._bus.publish(PotAwarded(winner, share + extra, reason, best))

    def _showdown_order(self, players: list[Player], button: Player) -> list[Player]:
        """De laatste agressor toont eerst; anders de eerste speler links van de button."""
        first = self._last_aggressor if self._last_aggressor in players else None
        if first is None:
            return Table.rotate_after(players, button)
        return Table.rotate_from(players, first)

    def best_hand(self, player: Player, hand: HandContext) -> HandValue:
        return self._evaluator.best_hand(player.hole_cards, hand.board)
