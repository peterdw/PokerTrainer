"""Starthandmodellen: Chen-formule en rangetabel op dezelfde schaal."""

import pytest

from pokertrainer.cards import parse_cards
from pokertrainer.starting_hands import (
    CALL_RAISE,
    HAND_MODELS,
    OPEN,
    PREMIUM,
    ChenModel,
    RangeChartModel,
    all_labels,
    combos,
    hand_model,
    normalize_label,
    parse_range,
)

CHEN = HAND_MODELS["beginner"]
CHART = HAND_MODELS["gevorderd"]
UTG, BTN = "vroeg (under the gun)", "button"


def test_all_169_hand_types_and_1326_combos():
    labels = all_labels()
    assert len(labels) == 169 and len(set(labels)) == 169
    assert sum(combos(label) for label in labels) == 1326


def test_normalize_label():
    assert normalize_label("k5o") == "K5o"
    assert normalize_label("5Ks") == "K5s"
    assert normalize_label("qq") == "QQ"
    for bad in ("K5", "QQs", "Z9o", "K"):
        with pytest.raises(ValueError):
            normalize_label(bad)


def test_parse_range_notation():
    assert parse_range("JJ+") == {"JJ", "QQ", "KK", "AA"}
    assert parse_range("ATs+") == {"ATs", "AJs", "AQs", "AKs"}
    assert parse_range("75s+ KQo") == {"75s", "76s", "KQo"}


def test_chart_is_nested_and_ranked_sensibly():
    assert isinstance(CHART, RangeChartModel)
    widths = [CHART.width[position] for position, _ in CHART.ranges]
    assert widths == sorted(widths)  # van krap naar ruim
    assert CHART.ranking[:4] == ["AA", "KK", "QQ", "JJ"]
    assert CHART.rank["72o"] > CHART.rank["K5o"] > CHART.rank["AKs"]
    assert CHART.earliest_position("K5o") is None
    assert CHART.earliest_position("K9s") == "midden"


@pytest.mark.parametrize("model", HAND_MODELS.values())
def test_models_agree_on_extremes(model):
    for position in (UTG, BTN):
        aces = model.assess(parse_cards("As Ah"), position)
        junk = model.assess(parse_cards("7d 2c"), position)
        assert aces.premium and aces.value >= PREMIUM
        assert not junk.playable and junk.value < OPEN
        assert aces.strength > 0.95 > 0.1 > junk.strength
        assert aces.lines and junk.lines


def test_position_and_looseness_widen_the_playable_range():
    hand = parse_cards("Kh 9h")  # K9s
    for model in HAND_MODELS.values():
        early = model.assess(hand, UTG, looseness=0.15)
        late = model.assess(hand, BTN, looseness=0.15)
        loose = model.assess(hand, UTG, looseness=0.9)
        assert late.value > early.value
        assert loose.value > early.value
        assert model.assess(hand, BTN).playable  # een gemiddelde speler opent K9s op de button


def test_chart_value_matches_the_table_for_an_average_player():
    # K9s staat vanaf 'midden' in de tabel: niet onder de gun, wel vanaf midden.
    assert not CHART.assess_label("K9s", UTG).playable
    assert CHART.assess_label("K9s", "midden").playable
    assert CHART.assess_label("AQs", UTG).worth_a_call
    assert CHART.assess_label("K5o", BTN).verdict in ("marginaal", "zwak")


def test_chen_value_scale_matches_old_thresholds():
    assert ChenModel.value_for(11, 7) >= PREMIUM
    assert ChenModel.value_for(9, 7) >= CALL_RAISE > ChenModel.value_for(8, 7)
    assert ChenModel.value_for(7, 7) == OPEN > ChenModel.value_for(6, 7)


def test_hand_model_lookup():
    assert hand_model(None) is CHEN
    assert hand_model("gevorderd") is CHART
    with pytest.raises(ValueError):
        hand_model("expert")
