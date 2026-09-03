from pokertrainer.cards import parse_cards
from pokertrainer.coach import flush_draw, straight_outs
from pokertrainer.strategies import chen_score, hand_label


def test_chen_scores_of_known_hands():
    assert chen_score(parse_cards("As Ks")) == 12
    assert chen_score(parse_cards("Ah Ad")) == 20
    assert chen_score(parse_cards("Kc Kd")) == 16
    assert chen_score(parse_cards("2c 2d")) == 5
    assert chen_score(parse_cards("7d 2c")) == -1
    assert chen_score(parse_cards("Jh Th")) == 9


def test_hand_label():
    assert hand_label(parse_cards("As Ks")) == "AKs"
    assert hand_label(parse_cards("9d Tc")) == "T9o"
    assert hand_label(parse_cards("Qc Qd")) == "QQ"


def test_draw_detection():
    assert flush_draw(parse_cards("Ah Kh 7h 2h 9c")).value == "♥"
    assert flush_draw(parse_cards("Ah Kh 7h 2c 9c")) is None
    assert straight_outs(parse_cards("9c 8d 7h 6s 2c")) == 2  # open-ended: 5 of T
    assert straight_outs(parse_cards("9c 8d 6h 5s 2c")) == 1  # gutshot: 7
    assert straight_outs(parse_cards("9c 8d 7h 6s 5c")) == 0  # al een straight
