"""Starthandmodellen: hoe sterk zijn je twee eigen kaarten vóór de flop?

Patroon: Strategy. Coach en bots vragen alleen ``model.assess(...)``; welk model
erachter zit is een instelling ("coachmethode"):

- ``ChenModel``       (beginner)  de Chen-formule: een puntentelling die je zelf kunt narekenen.
- ``RangeChartModel`` (gevorderd) een rangetabel per positie, zoals spelers het in de praktijk leren.

Beide modellen vertalen hun oordeel naar dezelfde schaal ``value`` (0..1), zodat
de botlogica niets van het model hoeft te weten:

    value >= PREMIUM     (0.90)  premium: raisen en re-raisen
    value >= CALL_RAISE  (0.62)  goed genoeg om een raise te betalen
    value >= OPEN        (0.50)  speelbaar: openen of meedoen
    lager                        fold

Daarnaast geeft elk model ``strength``: het aandeel van alle starthanden dat
zwakker is, onafhankelijk van positie en speelstijl.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Sequence

from .cards import Card, Rank, Suit

RANK_LABELS = "23456789TJQKA"
TOTAL_COMBOS = 1326  # 52 boven 2

PREMIUM = 0.90
CALL_RAISE = 0.62
OPEN = 0.50


# --- notatie ----------------------------------------------------------------
def hand_label(cards: Sequence[Card]) -> str:
    """``A♠ K♠`` -> ``AKs``, ``T♥ 9♦`` -> ``T9o``, ``Q♣ Q♦`` -> ``QQ``."""
    high, low = sorted(cards, reverse=True)
    if high.rank == low.rank:
        return f"{high.rank.label}{low.rank.label}"
    suffix = "s" if high.suit == low.suit else "o"
    return f"{high.rank.label}{low.rank.label}{suffix}"


def normalize_label(text: str) -> str:
    """``k5o`` -> ``K5o``, ``5Ko`` -> ``K5o``, ``qq`` -> ``QQ``. ValueError bij onzin."""
    text = text.strip().replace(" ", "")
    if len(text) not in (2, 3):
        raise ValueError(f"Onbekende starthand: {text!r}")
    first, second = text[0].upper(), text[1].upper()
    if first not in RANK_LABELS or second not in RANK_LABELS:
        raise ValueError(f"Onbekende starthand: {text!r}")
    if RANK_LABELS.index(first) < RANK_LABELS.index(second):
        first, second = second, first
    if first == second:
        if len(text) == 3:
            raise ValueError("Een paar schrijf je zonder s of o, bijvoorbeeld QQ.")
        return first + second
    suffix = text[2].lower() if len(text) == 3 else ""
    if suffix not in ("s", "o"):
        raise ValueError("Zet achter twee verschillende kaarten een s (suited) of o (offsuit), bijvoorbeeld K5o.")
    return first + second + suffix


def label_cards(label: str) -> list[Card]:
    """Representatieve kaarten voor een starthandlabel."""
    label = normalize_label(label)
    high, low = Rank.from_label(label[0]), Rank.from_label(label[1])
    if len(label) == 2:
        return [Card.of(high, Suit.SPADES), Card.of(low, Suit.HEARTS)]
    second_suit = Suit.SPADES if label[2] == "s" else Suit.HEARTS
    return [Card.of(high, Suit.SPADES), Card.of(low, second_suit)]


def combos(label: str) -> int:
    """Aantal kaartcombinaties: een paar 6, suited 4, offsuit 12."""
    if len(label) == 2:
        return 6
    return 4 if label.endswith("s") else 12


def all_labels() -> list[str]:
    """Alle 169 starthandtypes."""
    labels = []
    for i, high in enumerate(reversed(RANK_LABELS)):
        for low in list(reversed(RANK_LABELS))[i:]:
            if high == low:
                labels.append(high + low)
            else:
                labels.append(high + low + "s")
                labels.append(high + low + "o")
    return labels


def is_late(position: str) -> bool:
    return position.startswith(("button", "cutoff"))


# --- Chen-formule -------------------------------------------------------------
def chen_breakdown(cards: Sequence[Card]) -> list[tuple[str, float]]:
    """De onderdelen van de Chen-formule: (omschrijving, punten). Som + afronden naar boven = score."""
    high, low = sorted(cards, reverse=True)
    base = {Rank.ACE: 10.0, Rank.KING: 8.0, Rank.QUEEN: 7.0, Rank.JACK: 6.0}.get(high.rank, high.rank.value / 2)
    parts = [(f"hoogste kaart {high.rank.dutch_name}", base)]
    if high.rank == low.rank:
        parts.append(("paar: punten verdubbeld (minimaal 5)", max(5.0, base * 2) - base))
        return parts
    if high.suit == low.suit:
        parts.append(("suited", 2.0))
    gap = high.rank.value - low.rank.value - 1
    penalty = {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
    if penalty:
        parts.append((f"gat van {gap} kaart{'en' if gap > 1 else ''}", -float(penalty)))
    if gap <= 1 and high.rank.value < Rank.QUEEN.value:
        parts.append(("aansluitend onder de vrouw", 1.0))
    return parts


def chen_score(cards: Sequence[Card]) -> int:
    """Chen-formule: een klassieke score (ongeveer -1 .. 20) voor starthanden."""
    return math.ceil(sum(points for _, points in chen_breakdown(cards)))


def chen_explanation(cards: Sequence[Card]) -> str:
    """``"hoogste kaart heer 8, gat van 7 kaarten -5 = 3"``"""

    def number(points: float, signed: bool) -> str:
        text = f"{points:g}".replace(".", ",")
        return f"+{text}" if signed and points > 0 else text

    parts = chen_breakdown(cards)
    pieces = [f"{label} {number(points, index > 0)}" for index, (label, points) in enumerate(parts)]
    return ", ".join(pieces) + f" = {chen_score(cards)}"


def starting_hand_class(score: int) -> str:
    if score >= 12:
        return "premium"
    if score >= 9:
        return "sterk"
    if score >= 7:
        return "speelbaar"
    if score >= 5:
        return "marginaal"
    return "zwak"


# --- het contract -------------------------------------------------------------
@dataclass(frozen=True)
class HandAssessment:
    label: str
    value: float  # positie- en stijlafhankelijk, zie module-docstring
    strength: float  # aandeel van alle starthanden dat zwakker is (0..1)
    verdict: str  # premium / sterk / speelbaar / marginaal / zwak
    lines: tuple[str, ...]

    @property
    def playable(self) -> bool:
        return self.value >= OPEN

    @property
    def premium(self) -> bool:
        return self.value >= PREMIUM

    @property
    def worth_a_call(self) -> bool:
        return self.value >= CALL_RAISE


class StartingHandModel(ABC):
    key: str = ""
    name: str = ""
    description: str = ""

    @abstractmethod
    def assess(self, cards: Sequence[Card], position: str, looseness: float = 0.5) -> HandAssessment: ...

    def assess_label(self, label: str, position: str, looseness: float = 0.5) -> HandAssessment:
        return self.assess(label_cards(label), position, looseness)


# --- model 1: Chen ------------------------------------------------------------
class ChenModel(StartingHandModel):
    key = "beginner"
    name = "Beginner: Chen-formule"
    description = (
        "Een puntentelling voor je twee kaarten: hoogste kaart, paar, suited en het gat ertussen. "
        "Makkelijk zelf na te rekenen, ideaal om te leren waarom een hand sterk of zwak is."
    )

    def __init__(self) -> None:
        scores = {label: chen_score(label_cards(label)) for label in all_labels()}
        self._strength: dict[str, float] = {}
        for label, score in scores.items():
            lower = sum(combos(other) for other, s in scores.items() if s < score)
            equal = sum(combos(other) for other, s in scores.items() if s == score and other != label)
            self._strength[label] = (lower + equal / 2) / TOTAL_COMBOS

    @staticmethod
    def open_threshold(looseness: float) -> float:
        """Hoe losser de speler, hoe lager de grens om te openen (9 punten krap, 5 punten los)."""
        return 9 - 4 * looseness

    @staticmethod
    def value_for(score: float, threshold: float) -> float:
        if score >= 11:
            return min(1.0, 0.9 + 0.1 * (score - 11) / 9)
        if score >= threshold:
            return 0.5 + 0.4 * (score - threshold) / (11 - threshold)
        return max(0.0, 0.5 * (1 - (threshold - score) / 6))

    def assess(self, cards: Sequence[Card], position: str, looseness: float = 0.5) -> HandAssessment:
        label = hand_label(cards)
        score = chen_score(cards)
        lines = [f"Starthand {label}: Chen-score {chen_explanation(cards)} van 20 ({starting_hand_class(score)})."]
        if is_late(position):
            score += 1
            lines.append("Late positie: je mag iets meer handen spelen (+1).")
        threshold = self.open_threshold(looseness)
        lines.append(f"Openen vanaf {threshold:g} punten voor deze speelstijl; premium vanaf 11.")
        return HandAssessment(
            label=label,
            value=self.value_for(score, threshold),
            strength=self._strength[label],
            verdict=starting_hand_class(score),
            lines=tuple(lines),
        )


# --- model 2: rangetabel ------------------------------------------------------
def parse_range(text: str) -> set[str]:
    """Pokernotatie naar handlabels: ``"77+ A9s+ KQo T9s"`` -> {"77", ..., "AA", "A9s", ..., "AKs", "KQo", "T9s"}."""
    labels: set[str] = set()
    for token in text.split():
        plus = token.endswith("+")
        core = token[:-1] if plus else token
        first, second = core[0], core[1]
        suffix = core[2:] if len(core) > 2 else ""
        if first == second:  # paar
            start = RANK_LABELS.index(first)
            stop = len(RANK_LABELS) if plus else start + 1
            labels.update(RANK_LABELS[i] * 2 for i in range(start, stop))
            continue
        if suffix not in ("s", "o"):
            raise ValueError(f"Ongeldige range-notatie: {token!r}")
        high = RANK_LABELS.index(first)
        low = RANK_LABELS.index(second)
        stop = high if plus else low + 1
        labels.update(first + RANK_LABELS[i] + suffix for i in range(low, stop))
    return labels


# Cumulatieve openingsranges (6-max, "raise first in"), van krap naar ruim.
# Elke range bevat de vorige; dat wordt bij het laden gecontroleerd.
CHART_POSITIONS: list[tuple[str, str]] = [
    ("vroeg (under the gun)", "22+ ATs+ KTs+ QTs+ JTs T9s 98s AJo+ KQo"),
    ("midden", "22+ A8s+ K9s+ Q9s+ J9s+ T9s 98s 87s ATo+ KJo+ QJo"),
    ("cutoff (laat)", "22+ A2s+ K7s+ Q8s+ J8s+ T8s+ 97s+ 86s+ 75s+ 65s A9o+ KTo+ QTo+ JTo"),
    ("small blind", "22+ A2s+ K5s+ Q8s+ J7s+ T8s+ 97s+ 86s+ 75s+ 65s A7o+ K9o+ QTo+ JTo T9o"),
    ("button", "22+ A2s+ K2s+ Q5s+ J6s+ T6s+ 96s+ 85s+ 75s+ 64s+ 54s A2o+ K8o+ Q9o+ J9o+ T9o 98o"),
]
# De big blind verdedigt ruim (hij heeft al geld in de pot); heads-up is de button ook small blind.
POSITION_ALIASES = {"big blind": "button", "button (small blind)": "button"}
PREMIUM_COUNT = 8  # de topacht van de rangorde: AA KK QQ JJ AKs AQs TT AKo


class RangeChartModel(StartingHandModel):
    key = "gevorderd"
    name = "Gevorderd: rangetabel per positie"
    description = (
        "Zoals spelers het in de praktijk leren: per positie een vaste lijst handen die je opent, "
        "van krap onder de gun tot ruim op de button. Geen rekenwerk, wel uit het hoofd leren."
    )

    def __init__(self) -> None:
        self.ranges: list[tuple[str, set[str]]] = []
        previous: set[str] = set()
        for position, text in CHART_POSITIONS:
            labels = parse_range(text)
            missing = previous - labels
            if missing:
                raise ValueError(f"Range voor {position} mist handen uit de krappere range: {sorted(missing)}")
            self.ranges.append((position, labels))
            previous = labels
        # Rangorde: hoe vroeger een hand geopend mag worden, hoe hoger; binnen een laag beslist Chen.
        order: list[str] = []
        seen: set[str] = set()
        for _, labels in self.ranges:
            order.extend(sorted(labels - seen, key=self._sort_key))
            seen |= labels
        order.extend(sorted(set(all_labels()) - seen, key=self._sort_key))
        self.ranking: list[str] = order
        self.rank: dict[str, int] = {label: index for index, label in enumerate(order)}
        self.width: dict[str, int] = {position: len(labels) for position, labels in self.ranges}
        self.share: dict[str, float] = {
            position: sum(combos(label) for label in labels) / TOTAL_COMBOS for position, labels in self.ranges
        }

    @staticmethod
    def _sort_key(label: str) -> tuple:
        kind = 0 if len(label) == 2 else 1 if label.endswith("s") else 2
        return (-chen_score(label_cards(label)), kind, -RANK_LABELS.index(label[0]), -RANK_LABELS.index(label[1]))

    def chart_position(self, position: str) -> str:
        position = POSITION_ALIASES.get(position, position)
        return position if position in self.width else "midden"

    def top_share(self, label: str) -> float:
        """Aandeel van alle kaartcombinaties dat op of boven deze hand staat."""
        rank = self.rank[label]
        return sum(combos(other) for other in self.ranking[: rank + 1]) / TOTAL_COMBOS

    def earliest_position(self, label: str) -> str | None:
        for position, labels in self.ranges:
            if label in labels:
                return position
        return None

    def assess(self, cards: Sequence[Card], position: str, looseness: float = 0.5) -> HandAssessment:
        label = hand_label(cards)
        rank = self.rank[label]
        chart = self.chart_position(position)
        chart_width = self.width[chart]
        factor = 0.6 + 0.8 * looseness  # krap 0.6x, gemiddeld 1x, los 1.4x de tabel
        width = max(PREMIUM_COUNT, min(len(self.ranking), round(chart_width * factor)))
        top = self.top_share(label)
        lines = [f"Starthand {label}: plaats {rank + 1} van 169 in de rangorde (top {top:.0%} van alle handen)."]
        style = ""
        if factor <= 0.85:
            style = f" Een krappe speler opent minder ({width} in plaats van {chart_width} handtypes)."
        elif factor >= 1.15:
            style = f" Een losse speler speelt ruimer ({width} in plaats van {chart_width} handtypes)."
        lines.append(f"Rangetabel voor '{chart}': ongeveer de beste {self.share[chart]:.0%} van de handen.{style}")

        if rank < PREMIUM_COUNT:
            value = 0.9 + 0.1 * (1 - rank / PREMIUM_COUNT)
            verdict = "premium"
            lines.append("Topacht van alle starthanden: premium, hier raise je overal mee.")
        elif rank < width:
            value = 0.5 + 0.39 * (1 - (rank - PREMIUM_COUNT) / max(1, width - PREMIUM_COUNT))
            verdict = "sterk" if value >= CALL_RAISE else "speelbaar"
            note = " Sterk genoeg om ook een raise te betalen." if value >= CALL_RAISE else " Tegen een raise liever folden."
            lines.append(f"Binnen de range voor deze positie: speelbaar.{note}")
        else:
            value = 0.5 * (1 - (rank - width) / max(1, len(self.ranking) - width))
            earliest = self.earliest_position(label)
            verdict = "marginaal" if earliest is not None and rank < width * 1.35 else "zwak"
            if earliest is not None:
                lines.append(f"Buiten de range voor deze positie; volgens de tabel speel je {label} pas vanaf '{earliest}'.")
            else:
                lines.append(f"{label} staat in geen enkele openingsrange: fold.")
        return HandAssessment(
            label=label,
            value=value,
            strength=1 - top,
            verdict=verdict,
            lines=tuple(lines),
        )

    def summary_lines(self) -> list[str]:
        """Korte samenvatting van de tabel, voor de les."""
        return [
            f"• {position}: ongeveer de beste {self.share[position]:.0%} van de handen ({self.width[position]} van 169 handtypes)."
            for position, _ in self.ranges
        ]


# --- register -----------------------------------------------------------------
HAND_MODELS: dict[str, StartingHandModel] = {model.key: model for model in (ChenModel(), RangeChartModel())}
DEFAULT_MODEL_KEY = ChenModel.key


def hand_model(key: str | None) -> StartingHandModel:
    try:
        return HAND_MODELS[key or DEFAULT_MODEL_KEY]
    except KeyError as error:
        raise ValueError(f"Onbekende coachmethode: {key!r}. Kies uit: {', '.join(HAND_MODELS)}.") from error


def model_keys() -> Iterable[str]:
    return HAND_MODELS.keys()
