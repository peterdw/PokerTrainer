"""Push-or-fold voor korte stacks en verdedigen tegen een raise."""

import random

from pokertrainer.actions import ActionType, LegalActions
from pokertrainer.cards import parse_cards
from pokertrainer.coach import COACH_PROFILE
from pokertrainer.context import DecisionContext, OpponentInfo
from pokertrainer.equity import EquityCalculator
from pokertrainer.evaluation import HandEvaluator
from pokertrainer.players import Player
from pokertrainer.push_fold import NASH, PUSH_FOLD_LIMIT
from pokertrainer.rules_content import RULE_PAGES, RULE_QUIZ
from pokertrainer.starting_hands import CALL_RAISE, HAND_MODELS, ChenModel, all_labels
from pokertrainer.strategies import HeuristicBotStrategy, ScriptedStrategy

CHART = HAND_MODELS["gevorderd"]
CHEN = HAND_MODELS["beginner"]
UTG, BTN, SB, BB = "vroeg (under the gun)", "button", "small blind", "big blind"


def test_nash_table_is_complete_and_consistent():
    assert set(NASH.limit) == set(all_labels())
    assert NASH.limit["AA"] == 20 and NASH.limit["A2o"] == 20 and NASH.limit["72o"] == 2.5
    assert NASH.limit["AKs"] == 20 and NASH.limit["72s"] == 4.5 and NASH.limit["K5o"] == 16
    for label in all_labels():
        if len(label) == 3 and label.endswith("o"):
            assert NASH.limit[label[:2] + "s"] >= NASH.limit[label], label  # suited duwt verder dan offsuit


def test_push_ranking_is_monotonic_in_kicker_and_suitedness():
    rank = NASH.rank
    assert NASH.ranking[:3] == ["AA", "KK", "QQ"]
    assert rank["A9s"] < rank["A2s"] and rank["A9o"] < rank["A2o"]
    assert rank["K8s"] < rank["K2s"]
    assert rank["ATo"] < rank["JTo"]
    assert rank["22"] < rank["T9o"]
    assert rank["AKo"] < rank["TT"] < rank["AQs"] < rank["AQo"] < rank["99"]
    assert rank["72o"] > 160


def test_heads_up_small_blind_decides_by_the_table_itself():
    for label in ("Q7o", "K5o", "A2o", "72o", "J4s"):
        cards = parse_cards(f"{label[0]}h {label[1]}{'h' if label.endswith('s') else 'd'}")
        limit = NASH.limit[label]
        assert NASH.pushing(cards, limit, SB, 1).go, f"{label} duw je precies tot {limit}"
        if limit < 20:
            assert not NASH.pushing(cards, limit + 0.5, SB, 1).go, f"{label} niet boven {limit}"
    advice = NASH.pushing(parse_cards("Qh 7d"), 15, SB, 1)
    assert not advice.go and "tot 14 big blinds" in advice.lines[1] and "15 big blinds" in advice.lines[1]
    assert NASH.pushing(parse_cards("Qh 7d"), 12, SB, 1).go


def test_pushing_depends_on_stack_and_callers():
    aces, k5o, junk = parse_cards("As Ah"), parse_cards("Kh 5d"), parse_cards("7d 2c")
    for callers, position in ((5, UTG), (2, BTN), (1, SB)):
        assert NASH.pushing(aces, 8, position, callers).go
        assert not NASH.pushing(junk, 8, position, callers).go
    assert NASH.pushing(k5o, 8, SB, 1).go, "heads-up duw je K5o met 8 big blinds"
    assert not NASH.pushing(k5o, 8, UTG, 5).go, "onder de gun met vijf spelers die kunnen callen niet"
    assert NASH.push_share(4, 2, BTN) > NASH.push_share(11, 2, BTN)
    lines = " ".join(NASH.pushing(k5o, 8, UTG, 5).lines)
    assert "5 tegenstanders die je all-in nog kunnen callen" in lines and "sterkere hand" in lines


def test_shares_are_combo_shares_and_types_are_reported():
    advice = NASH.pushing(parse_cards("Kh 5d"), 10, UTG, 5)
    types = int(advice.lines[2].split("(")[1].split(" van")[0])
    assert abs(NASH.combo_share(types) - advice.share) < 0.03
    assert 0.10 <= advice.share <= 0.20


def test_calling_and_reshoving_are_tighter_than_pushing():
    k5o, queens = parse_cards("Kh 5d"), parse_cards("Qs Qd")
    assert NASH.pushing(k5o, 8, SB, 1).go
    assert not NASH.calling(k5o, 8).go
    assert not NASH.reshoving(k5o, 8, 2.5, 2, BTN).go
    assert NASH.calling(queens, 8).go and NASH.reshoving(queens, 8, 2.5, 2, BTN).go
    assert NASH.call_share(8) < NASH.reshove_share(8, 1, BTN) < NASH.push_share(8, 1, BTN)
    covered = NASH.calling(parse_cards("As 2d"), 12, 20)
    smaller = NASH.calling(parse_cards("As 2d"), 12, 3)
    assert "hele stack" in covered.lines[0] and "all-in van 3" in smaller.lines[0]
    assert smaller.go and smaller.action == "call"


def _context(hole, position, stack, current_bet, opponents, big_blind=100, my_bet=0):
    player = Player("Ik", stack, ScriptedStrategy([]), is_human=False)
    player.bet_this_street = my_bet
    to_call = min(current_bet - my_bet, stack)
    legal = LegalActions(
        can_check=to_call == 0,
        call_amount=to_call,
        can_raise=stack + my_bet > current_bet,
        min_raise_to=min(current_bet + big_blind, stack + my_bet),
        max_raise_to=stack + my_bet,
    )
    return DecisionContext(
        player=player,
        hole_cards=tuple(parse_cards(hole)),
        board=(),
        street="preflop",
        pot=current_bet + sum(o.bet_this_street for o in opponents),
        current_bet=current_bet,
        legal=legal,
        big_blind=big_blind,
        position=position,
        players_to_act_after=0,
        contenders=1 + sum(1 for o in opponents if not o.folded),
        opponents=tuple(opponents),
    )


def _coach_strategy():
    evaluator = HandEvaluator()
    return HeuristicBotStrategy(COACH_PROFILE, evaluator, EquityCalculator(evaluator, random.Random(1), 20), mix=False)


def test_short_stack_facing_a_normal_raise_reshoves_only_with_a_strong_hand():
    strategy = _coach_strategy()
    raiser = OpponentInfo("UTG", 4800, 200, False, False, UTG)
    blinds = [OpponentInfo("SB", 4950, 50, False, False, SB), OpponentInfo("BB", 4900, 100, False, False, BB)]
    weak = strategy.reason(_context("Qh 9d", BTN, 1200, 200, [raiser, *blinds]))
    strong = strategy.reason(_context("Ah Jd", BTN, 1200, 200, [raiser, *blinds]))
    assert weak.action.type is ActionType.FOLD and "raise naar 2" in weak.reasons[0]
    assert strong.action.type is ActionType.ALL_IN and "re-shove" in " ".join(strong.reasons)


def test_short_stack_facing_an_all_in_calls_the_smaller_stack_and_shoves_when_covered():
    strategy = _coach_strategy()
    shover = OpponentInfo("CO", 0, 300, False, True, "cutoff (laat)")
    deep = [OpponentInfo("SB", 3000, 50, False, False, SB), OpponentInfo("BB", 3000, 100, False, False, BB)]
    call = strategy.reason(_context("Ah 2d", BTN, 1200, 300, [shover, *deep]))
    assert call.action.type is ActionType.CALL and "all-in van 3" in call.reasons[0]
    covered = OpponentInfo("UTG", 0, 2000, False, True, UTG)
    shove = strategy.reason(_context("Ah Kd", BTN, 1200, 2000, [covered, *deep]))
    assert shove.action.type is ActionType.ALL_IN and "hele stack" in shove.reasons[0]


def test_defending_against_a_raise_uses_position_and_the_big_blind_discount():
    assert CHART.defend_label("QQ", "midden").premium
    assert CHART.defend_label("A5o", BB).worth_a_call, "de big blind verdedigt ruim"
    assert not CHART.defend_label("A5o", UTG).playable, "buiten positie is A5o een fold tegen een raise"
    assert CHART.defend_label("T9s", BTN).worth_a_call and not CHART.defend_label("T9s", UTG).worth_a_call
    assert "geen enkele openingsrange" in CHART.defend_label("K5o", BTN).lines[-1]
    assert "pas vanaf" in CHART.defend_label("K9s", UTG).lines[-1]
    assert CHEN.defend_label("A5o", BB).value > CHEN.defend_label("A5o", SB).value, "Chen geeft de big blind een korting"
    for model in (CHART, CHEN):
        defended = model.defend_label("K5o", BTN)
        assert not defended.playable and not defended.worth_a_call
        assert "fold" in defended.lines[-1].lower()


def test_chen_text_thresholds_match_the_decision():
    for looseness in (0.0, 0.15, 0.45, 0.5, 0.9, 1.0):
        call_points = ChenModel.call_points(looseness)
        threshold = ChenModel.open_threshold(looseness)
        assert ChenModel.value_for(call_points, threshold) >= CALL_RAISE > ChenModel.value_for(call_points - 1, threshold)
        assert ChenModel.value_for(ChenModel.open_points(looseness), threshold) >= 0.5
    lines = CHEN.defend_label("T9s", BTN, 0.45).lines
    assert f"Minstens {ChenModel.call_points(0.45)} punten" in " ".join(lines)
    assert lines[-1].startswith("T9s heeft 9 punten")


def test_chart_premium_set_equals_the_three_bet_range():
    assert CHART.ranking[:8] == ["AA", "KK", "QQ", "JJ", "AKs", "AQs", "TT", "AKo"]
    assert CHART.assess_label("AKo", UTG).premium and not CHART.assess_label("AJs", UTG).premium


def test_lesson_uses_one_push_fold_limit_and_short_lines():
    texts = [line for _, lines in RULE_PAGES for line in lines] + [explanation for *_, explanation in RULE_QUIZ]
    for text in texts:
        assert "minder dan ± 10 big blinds" not in text and "minder dan ongeveer 10 big blinds" not in text
    assert any(f"± {PUSH_FOLD_LIMIT:.0f} big blinds" in text for text in texts)
    assert all(len(line) <= 108 for _, lines in RULE_PAGES for line in lines)
