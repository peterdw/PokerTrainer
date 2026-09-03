import pytest

from pokertrainer.actions import Action, ActionType, IllegalActionError, RaiseCommand
from pokertrainer.betting import BettingRound
from pokertrainer.context import DecisionContext
from pokertrainer.events import EventBus, PlayerActed
from pokertrainer.players import Player
from pokertrainer.strategies import ScriptedStrategy


class Recorder:
    def __init__(self):
        self.events = []

    def notify(self, event):
        self.events.append(event)


def make_players(*scripts, chips=1000):
    players = []
    for index, script in enumerate(scripts):
        player = Player(f"P{index}", chips, ScriptedStrategy(script))
        player.seat = index
        players.append(player)
    return players


def make_round(players, current_bet=0, big_blind=50):
    bus = EventBus()
    recorder = Recorder()
    bus.subscribe(recorder)
    holder = {}

    def context_factory(player, legal):
        return DecisionContext(
            player, (), (), "flop", sum(p.invested_this_hand for p in players),
            holder["round"].current_bet, legal, big_blind, "midden", 0,
            sum(1 for p in players if p.is_contender), (),
        )

    betting_round = BettingRound(
        players, big_blind, bus, "flop", context_factory,
        lambda: sum(p.invested_this_hand for p in players), current_bet,
    )
    holder["round"] = betting_round
    return betting_round, recorder


def test_min_raise_must_match_previous_raise_size():
    a, b, c = make_players([Action(ActionType.BET, 100)], [], [])
    betting_round, _ = make_round([a, b, c])
    RaiseCommand(100).execute(betting_round, a)
    assert betting_round.legal_actions(b).min_raise_to == 200
    RaiseCommand(300).execute(betting_round, b)  # raise van 200
    assert betting_round.legal_actions(c).min_raise_to == 500
    with pytest.raises(IllegalActionError):
        RaiseCommand(400).execute(betting_round, c)


def test_short_all_in_does_not_reopen_action():
    a, b, c = make_players(
        [Action(ActionType.BET, 100), Action(ActionType.CALL)],
        [Action(ActionType.CALL), Action(ActionType.CALL)],
        [Action(ActionType.ALL_IN)],
    )
    c.chips = 150  # all-in voor 150 is een raise van 50: minder dan de minimale 100
    betting_round, _ = make_round([a, b, c])
    betting_round.run()
    assert c.all_in and c.bet_this_street == 150
    assert a.bet_this_street == 150 and b.bet_this_street == 150
    assert a.strategy.contexts[1].legal.can_raise is False
    assert b.strategy.contexts[1].legal.can_raise is False
    assert betting_round.min_raise_increment == 100


def test_full_raise_reopens_action():
    a, b, c = make_players(
        [Action(ActionType.BET, 100), Action(ActionType.CALL)],
        [Action(ActionType.CALL), Action(ActionType.CALL)],
        [Action(ActionType.RAISE, 300)],
    )
    betting_round, _ = make_round([a, b, c])
    betting_round.run()
    assert a.strategy.contexts[1].legal.can_raise is True
    assert all(p.bet_this_street == 300 for p in (a, b, c))
    assert betting_round.last_aggressor is c


def test_big_blind_gets_the_option_preflop():
    utg, sb, bb = make_players([Action(ActionType.CALL)], [Action(ActionType.CALL)], [Action(ActionType.RAISE, 150)])
    sb.commit(25)
    bb.commit(50)
    betting_round, recorder = make_round([utg, sb, bb], current_bet=50)
    betting_round.run()
    acted = [e.player.name for e in recorder.events if isinstance(e, PlayerActed)]
    assert acted == ["P0", "P1", "P2", "P0", "P1"]
    assert betting_round.current_bet == 150
    assert utg.folded and sb.folded  # lege scripts vallen terug op fold


def test_bot_illegal_action_falls_back_safely():
    a, b = make_players([Action(ActionType.RAISE, 5)], [])
    betting_round, recorder = make_round([a, b])
    betting_round.run()
    assert a.bet_this_street == 0 and not a.folded  # onwettige bet -> check
    assert all(not p.folded for p in (a, b))


def test_call_for_less_than_stack_goes_all_in():
    a, b = make_players([Action(ActionType.BET, 500)], [Action(ActionType.CALL)])
    b.chips = 200
    betting_round, recorder = make_round([a, b])
    betting_round.run()
    actions = [e.action.type for e in recorder.events if isinstance(e, PlayerActed)]
    assert actions == [ActionType.BET, ActionType.ALL_IN]
    assert b.all_in and b.bet_this_street == 200
