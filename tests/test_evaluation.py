import pytest

from pokertrainer.cards import parse_cards
from pokertrainer.evaluation import HandCategory, HandEvaluator

evaluator = HandEvaluator()


@pytest.mark.parametrize(
    "cards, category, kickers",
    [
        ("As Ks Qs Js Ts 2d 3c", HandCategory.ROYAL_FLUSH, (14,)),
        ("9h 8h 7h 6h 5h Ah Kd", HandCategory.STRAIGHT_FLUSH, (9,)),
        ("Ah 2h 3h 4h 5h Kd Qd", HandCategory.STRAIGHT_FLUSH, (5,)),
        ("Qc Qd Qh Qs 4d Ad 2c", HandCategory.FOUR_OF_A_KIND, (12, 14)),
        ("Jc Jd Jh 8s 8d 8c 2c", HandCategory.FULL_HOUSE, (11, 8)),
        ("Jc Jd Jh 8s 8d Ac Ad", HandCategory.FULL_HOUSE, (11, 14)),
        ("Kd 9d 7d 4d 2d Ad Ac", HandCategory.FLUSH, (14, 13, 9, 7, 4)),
        ("Tc 9d 8h 7s 6c 2d 2c", HandCategory.STRAIGHT, (10,)),
        ("Ac 2d 3h 4s 5c Kd Qc", HandCategory.STRAIGHT, (5,)),
        ("7c 7d 7h Ks 2d 4c 9d", HandCategory.THREE_OF_A_KIND, (7, 13, 9)),
        ("Ac Ad 9h 9s 5c 5d 2c", HandCategory.TWO_PAIR, (14, 9, 5)),
        ("Tc Td Ah 6s 3d 2c 9d", HandCategory.ONE_PAIR, (10, 14, 9, 6)),
        ("Ad Jc 8h 5s 2c 3d 9c", HandCategory.HIGH_CARD, (14, 11, 9, 8, 5)),
    ],
)
def test_categories(cards, category, kickers):
    value = evaluator.evaluate(parse_cards(cards))
    assert value.category is category
    assert value.kickers == kickers
    assert len(value.best_five) == 5


def test_kicker_decides_between_equal_pairs():
    board = parse_cards("Kc 7d 2h 9s 4c")
    ace_kicker = evaluator.best_hand(parse_cards("Kh Ad"), board)
    queen_kicker = evaluator.best_hand(parse_cards("Ks Qd"), board)
    assert ace_kicker > queen_kicker


def test_board_plays_gives_split():
    board = parse_cards("Ac Kc Qc Jc Tc")
    a = evaluator.best_hand(parse_cards("2d 3d"), board)
    b = evaluator.best_hand(parse_cards("4h 5h"), board)
    assert a == b
    assert a.category is HandCategory.ROYAL_FLUSH


def test_flush_beats_straight_and_full_house_beats_flush():
    flush = evaluator.evaluate(parse_cards("Kd 9d 7d 4d 2d"))
    straight = evaluator.evaluate(parse_cards("Tc 9d 8h 7s 6c"))
    full_house = evaluator.evaluate(parse_cards("Jc Jd Jh 8s 8d"))
    assert full_house > flush > straight


def test_describe_in_dutch():
    value = evaluator.evaluate(parse_cards("Jc Jd Jh 8s 8d"))
    assert value.describe() == "Full house, boeren vol met achten"


def test_rejects_wrong_card_count():
    with pytest.raises(ValueError):
        evaluator.evaluate(parse_cards("Ac Kc"))
