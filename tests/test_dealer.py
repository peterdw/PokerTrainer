import random

from pokertrainer.actions import Action, ActionType
from pokertrainer.dealer import PotCalculator
from pokertrainer.evaluation import HandEvaluator
from pokertrainer.events import EventBus, PlayerEliminated, PotAwarded, TournamentFinished
from pokertrainer.factory import create_bot_lineup
from pokertrainer.players import Player
from pokertrainer.session import Tournament
from pokertrainer.strategies import ScriptedStrategy
from pokertrainer.tournament import TournamentConfigBuilder, championship_sit_and_go


class Recorder:
    def __init__(self):
        self.events = []

    def notify(self, event):
        self.events.append(event)


def test_side_pots_follow_invested_amounts():
    a = Player("A", 0, ScriptedStrategy([]))
    b = Player("B", 700, ScriptedStrategy([]))
    c = Player("C", 700, ScriptedStrategy([]))
    d = Player("D", 950, ScriptedStrategy([]))
    a.chips = 100
    a.commit(100)  # all-in voor 100
    b.commit(300)
    c.commit(300)
    d.commit(50)
    d.fold()
    pots = PotCalculator.split([a, b, c, d])
    assert [(pot.amount, sorted(p.name for p in pot.eligible)) for pot in pots] == [
        (350, ["A", "B", "C"]),
        (400, ["B", "C"]),
    ]


def test_uncalled_bet_returns_to_bettor():
    a = Player("A", 1000, ScriptedStrategy([]))
    b = Player("B", 1000, ScriptedStrategy([]))
    a.commit(300)
    b.commit(100)
    b.fold()
    pots = PotCalculator.split([a, b])
    assert sum(pot.amount for pot in pots) == 400
    assert all(pot.eligible == [a] for pot in pots)


def test_everyone_folds_to_raise_awards_pot_without_showdown():
    rng = random.Random(1)
    bus = EventBus()
    recorder = Recorder()
    bus.subscribe(recorder)
    players = [
        Player("Button", 1000, ScriptedStrategy([Action(ActionType.RAISE, 150)])),
        Player("SB", 1000, ScriptedStrategy([Action(ActionType.FOLD)])),
        Player("BB", 1000, ScriptedStrategy([Action(ActionType.FOLD)])),
    ]
    config = TournamentConfigBuilder().starting_stack(1000).add_level(25, 50).hands_per_level(100).build()
    Tournament(config, players, bus, HandEvaluator(), rng).run(max_hands=1)
    awards = [e for e in recorder.events if isinstance(e, PotAwarded)]
    assert len(awards) == 1
    assert awards[0].player.name == "Button" and awards[0].amount == 225
    assert [p.chips for p in players] == [1075, 975, 950]


def test_bot_tournament_conserves_chips_and_produces_winner():
    rng = random.Random(42)
    evaluator = HandEvaluator()
    bots = create_bot_lineup(["rots", "maniak", "solide", "station", "prof"], 5000, evaluator, rng)
    bus = EventBus()
    recorder = Recorder()
    bus.subscribe(recorder)
    config = championship_sit_and_go()
    tournament = Tournament(config, bots, bus, evaluator, rng)
    winner = tournament.run()
    assert winner is not None
    assert winner.chips == 5 * 5000
    assert sum(p.chips for p in bots) == 5 * 5000
    eliminations = [e for e in recorder.events if isinstance(e, PlayerEliminated)]
    assert len(eliminations) == 4
    assert sorted(e.finishing_place for e in eliminations) == [2, 3, 4, 5]
    assert any(isinstance(e, TournamentFinished) for e in recorder.events)
    assert tournament.ranking[0] is winner and len(tournament.ranking) == 5


def test_chips_conserved_every_hand():
    rng = random.Random(7)
    evaluator = HandEvaluator()
    bots = create_bot_lineup(["maniak", "maniak", "station", "prof"], 2000, evaluator, rng)
    bus = EventBus()
    totals = []

    class Watcher:
        def notify(self, event):
            from pokertrainer.events import HandFinished

            if isinstance(event, HandFinished):
                totals.append(sum(p.chips for p in bots))

    bus.subscribe(Watcher())
    Tournament(championship_sit_and_go(), bots, bus, evaluator, rng).run(max_hands=40)
    assert totals and all(total == 4 * 2000 for total in totals)
