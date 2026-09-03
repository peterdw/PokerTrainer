"""Push-or-fold voor korte stacks (Nash-benadering).

Met een korte stack (minder dan ongeveer 12 big blinds) heeft een gewone raise
geen zin meer: na een call zit je vast aan de pot en kun je niet meer folden.
Je kiest dan tussen all-in en fold. Drie situaties:

- ``pushing``   niemand heeft geraised: zelf all-in gaan ("duwen") of folden.
- ``reshoving`` er ligt een gewone raise van een diepere speler: er all-in
                overheen gaan ("re-shove") of folden. Vraagt meer dan zelf duwen.
- ``calling``   er ligt een all-in (of een inzet die je stack dekt): callen of
                folden. Vraagt het meest: de duwer heeft het initiatief.

De tabel is een benadering van de bekende heads-up Nash-tabel (small blind
duwt): per starthand het aantal big blinds tot waar all-in gaan winstgevend is;
20 betekent "20 of meer". Heads-up in de small blind beslist die tabel
rechtstreeks. Met meer tegenstanders dient ze als rangorde ("welke handen duw je
het liefst") en bepaalt het aantal spelers dat je all-in nog kan callen hoeveel
van die rangorde je duwt: elke extra speler is een extra kans dat iemand een
sterkere hand heeft.

Aandelen zijn steeds een aandeel van alle 1326 kaartcombinaties, net als in de
rangetabel van ``starting_hands``; het aantal handtypes (van 169) staat erbij.
"""

from __future__ import annotations

import bisect
import itertools
from dataclasses import dataclass
from typing import Sequence

from .cards import Card
from .starting_hands import RANK_LABELS, TOTAL_COMBOS, combos, hand_label

PUSH_FOLD_LIMIT = 12.0  # big blinds: hieronder speel je push-or-fold

# Rijen = eerste kaart, kolommen = tweede kaart. Rechtsboven van de diagonaal
# suited (rij A, kolom K = AKs), linksonder offsuit (rij K, kolom A = AKo).
_NASH_GRID = """
     A    K    Q    J    T    9    8    7    6    5    4    3    2
A   20   20   20   20   20   20   20   20   20   20   20   20   20
K   20   20   20   20   20   20   20   20   20   20   20   20   20
Q   20   20   20   20   20   20   20   20   20   19   17   15   13
J   20   20   20   20   20   20   20   20   17   15   13   11   10
T   20   20   20   20   20   20   20   18   14   11   10    9    8
9   20   20   20   19   20   20   20   18   14   11  8.5  7.5  6.5
8   20   20   17   15   15   15   20   19   14   11    8    6  5.5
7   20   20   14   11   11   11   11   20   16   12    8  5.5  4.5
6   20   18   12    9    8    8    8    8   20   14   10  6.5  4.5
5   20   16   10    8  6.5  6.5    6    6  6.5   20   12    8    5
4   20   14    9    7    6    5  4.5  4.5    5  5.5   20  6.5  4.5
3   20   12    8    6  5.5  4.5  3.5    3  3.5    4  3.5   20    4
2   20   11    7  5.5    5    4    3  2.5  2.5    3  2.5  2.5   20
"""


def _parse_grid(text: str) -> dict[str, float]:
    lines = [line.split() for line in text.strip().splitlines()]
    columns = lines[0]
    limits: dict[str, float] = {}
    for row in lines[1:]:
        first, values = row[0], row[1:]
        for second, value in zip(columns, values):
            row_is_higher = RANK_LABELS.index(first) > RANK_LABELS.index(second)
            if first == second:
                label = first + second
            elif row_is_higher:  # rechts van de diagonaal: suited (rij A, kolom K = AKs)
                label = first + second + "s"
            else:  # links van de diagonaal: offsuit (rij K, kolom A = AKo)
                label = second + first + "o"
            limits[label] = float(value)
    return limits


def push_points(label: str) -> float:
    """Volgorde binnen een gelijke tabelgrens: wat wint het vaakst als het all-in tegen all-in gaat.

    Hoogste kaart telt dubbel, de kicker enkel, suited een half punt extra; een paar telt als
    een aas met een kicker drie hoger (zo staat 99 naast AQo en 22 naast A5o, zoals in
    gangbare push-rangordes).
    """
    high = RANK_LABELS.index(label[0]) + 2
    low = RANK_LABELS.index(label[1]) + 2
    if len(label) == 2:
        return 28 + min(high + 3, 17)
    return 2 * high + low + (0.5 if label.endswith("s") else 0.0)


@dataclass(frozen=True)
class PushFoldAdvice:
    go: bool  # all-in (duwen, re-shoven of callen)
    action: str  # "all-in" | "call" | "fold" | "check"
    share: float  # aandeel van de kaartcombinaties dat je in deze situatie speelt
    rank: int  # plaats van de hand in de push-rangorde (0 = beste)
    limit: float  # heads-up grens in big blinds
    lines: tuple[str, ...]


class NashPushFold:
    # Aandeel kaartcombinaties dat je bij 10 big blinds duwt, per aantal tegenstanders dat nog kan callen.
    BASE_PUSH_SHARE = {0: 0.85, 1: 0.50, 2: 0.38, 3: 0.27, 4: 0.20, 5: 0.15}
    BASE_CALL_SHARE = 0.20  # een all-in callen bij 10 big blinds
    RESHOVE_CALL_WEIGHT = 0.6  # re-shoven zit tussen callen (krap) en zelf duwen (ruim) in

    def __init__(self) -> None:
        self.limit = _parse_grid(_NASH_GRID)
        if len(self.limit) != 169:
            raise ValueError(f"De push-or-fold-tabel telt {len(self.limit)} handen in plaats van 169.")
        self.ranking = sorted(
            self.limit,
            key=lambda label: (
                -self.limit[label],
                -push_points(label),
                -RANK_LABELS.index(label[1]),
                0 if len(label) == 2 else 1 if label.endswith("s") else 2,
            ),
        )
        self.rank = {label: index for index, label in enumerate(self.ranking)}
        self._cumulative = list(itertools.accumulate(combos(label) / TOTAL_COMBOS for label in self.ranking))

    # --- rekenhulpjes -----------------------------------------------------------
    def types_for_share(self, share: float) -> int:
        """Aantal handtypes (van boven in de rangorde) dat samen ``share`` van de kaartcombinaties vormt."""
        return max(1, min(len(self.ranking), bisect.bisect_left(self._cumulative, share - 1e-9) + 1))

    def combo_share(self, types: int) -> float:
        return self._cumulative[max(0, min(len(self.ranking), types)) - 1] if types > 0 else 0.0

    @staticmethod
    def heads_up(position: str, callers: int) -> bool:
        """Small blind tegen alleen de big blind: precies de situatie waarvoor de tabel geldt."""
        return callers == 1 and position.startswith(("small blind", "button (small blind)"))

    @staticmethod
    def _stack_factor(stack_bb: float) -> float:
        """Hoe korter de stack, hoe ruimer: bij 5 big blinds ± 1,4x zo veel handen als bij 10."""
        return (10 / max(stack_bb, 1.0)) ** 0.5

    @staticmethod
    def _style_factor(looseness: float) -> float:
        return 0.8 + 0.4 * looseness

    def push_share(self, stack_bb: float, callers: int, position: str, looseness: float = 0.5) -> float:
        if self.heads_up(position, callers):
            return self.combo_share(sum(1 for label in self.ranking if self.limit[label] >= stack_bb))
        base = self.BASE_PUSH_SHARE[min(max(callers, 0), 5)]
        return min(0.85, max(0.05, base * self._stack_factor(stack_bb) * self._style_factor(looseness)))

    def call_share(self, effective_bb: float, looseness: float = 0.5) -> float:
        return min(0.6, max(0.03, self.BASE_CALL_SHARE * self._stack_factor(effective_bb) * self._style_factor(looseness)))

    def reshove_share(self, stack_bb: float, callers: int, position: str, looseness: float = 0.5) -> float:
        weight = self.RESHOVE_CALL_WEIGHT
        return weight * self.call_share(stack_bb, looseness) + (1 - weight) * self.push_share(stack_bb, callers, position, looseness)

    def _limit_text(self, label: str) -> str:
        limit = self.limit[label]
        return "20 big blinds of meer" if limit >= 20 else f"{limit:g}".replace(".", ",") + " big blinds"

    @staticmethod
    def _callers_text(callers: int) -> str:
        if callers == 1:
            return "1 tegenstander die je all-in nog kan callen"
        return f"{callers} tegenstanders die je all-in nog kunnen callen"

    # --- advies ---------------------------------------------------------------
    def pushing(self, cards: Sequence[Card], stack_bb: float, position: str, callers: int, looseness: float = 0.5) -> PushFoldAdvice:
        """Niemand heeft geraised: zelf all-in of fold."""
        label = hand_label(cards)
        rank = self.rank[label]
        limit = self.limit[label]
        lines = [
            f"Korte stack: {stack_bb:.1f} big blinds. Onder ± {PUSH_FOLD_LIMIT:.0f} big blinds is een gewone raise zinloos: "
            "na een call zit je vast aan de pot en kun je niet meer folden. Daarom: all-in ('duwen') of fold."
        ]
        if self.heads_up(position, callers):
            go = stack_bb <= limit
            allowed = sum(1 for other in self.ranking if self.limit[other] >= stack_bb)
            share = self.combo_share(allowed)
            lines.append(
                f"Push-or-fold-tabel (small blind tegen alleen de big blind): {label} duw je tot "
                f"{self._limit_text(label)}; jij hebt {stack_bb:.0f} big blinds."
            )
        else:
            share = self.push_share(stack_bb, callers, position, looseness)
            allowed = self.types_for_share(share)
            go = rank < allowed
            lines.append(
                f"Push-or-fold-rangorde: {label} staat op plaats {rank + 1} van 169 "
                f"(alleen heads-up duw je {label} tot {self._limit_text(label)}; hier zit je niet heads-up)."
            )
            lines.append(
                f"Met {self._callers_text(callers)} en {stack_bb:.0f} big blinds duw je ongeveer de beste "
                f"{share:.0%} van de handen ({allowed} van 169 handtypes): elke extra speler die kan callen "
                "vergroot de kans dat iemand een sterkere hand heeft."
            )
        if go:
            lines.append(
                f"{label} valt daarbinnen: all-in. Zo pak je vaak meteen de pot, en word je gecalld, "
                "dan speel je met een van de betere handen voor je hele stack."
            )
        else:
            lines.append(
                f"{label} valt erbuiten: fold. Met zo'n hand gecalld worden kost je je toernooi; "
                "met een betere hand verdubbelen brengt je terug in het spel."
            )
        return PushFoldAdvice(go, "all-in" if go else "fold", share, rank, limit, tuple(lines))

    def reshoving(self, cards: Sequence[Card], stack_bb: float, raise_bb: float, callers: int, position: str, looseness: float = 0.5) -> PushFoldAdvice:
        """Er ligt een gewone raise van een diepere speler: er all-in overheen of fold."""
        label = hand_label(cards)
        rank = self.rank[label]
        share = self.reshove_share(stack_bb, callers, position, looseness)
        allowed = self.types_for_share(share)
        go = rank < allowed
        lines = [
            f"Er ligt een raise naar {raise_bb:g} big blinds en jij hebt er {stack_bb:.0f}. Gewoon callen kan niet: "
            "na een call zit je vast aan de pot en kun je niet meer folden. Je gaat er all-in overheen "
            "(een 're-shove') of je past.",
            f"Dat vraagt een sterkere hand dan zelf als eerste duwen: de raiser heeft al kracht getoond en callt "
            f"vaker. Bij {stack_bb:.0f} big blinds re-shove je ongeveer de beste {share:.0%} van de handen "
            f"({allowed} van 169 handtypes); {label} staat op plaats {rank + 1}.",
        ]
        if go:
            lines.append(
                f"{label} valt daarbinnen: all-in over de raise. Zo dwing je de raiser tot een keuze voor zijn hele "
                "inzet en pak je vaak de pot meteen."
            )
        else:
            lines.append(
                f"{label} valt erbuiten: fold. Tegen een speler die al kracht toonde is dit geen hand om je toernooi "
                "op te zetten."
            )
        return PushFoldAdvice(go, "all-in" if go else "fold", share, rank, self.limit[label], tuple(lines))

    def calling(self, cards: Sequence[Card], stack_bb: float, bet_bb: float | None = None, looseness: float = 0.5) -> PushFoldAdvice:
        """Er ligt een all-in (of een inzet die je stack dekt): callen of fold.

        ``bet_bb`` is de inzet die er ligt; zonder waarde geldt een all-in die je stack dekt.
        Effectief staat het kleinste van beide op het spel.
        """
        label = hand_label(cards)
        rank = self.rank[label]
        bet_bb = stack_bb if bet_bb is None else bet_bb
        effective_bb = min(stack_bb, bet_bb)
        share = self.call_share(effective_bb, looseness)
        allowed = self.types_for_share(share)
        go = rank < allowed
        if bet_bb >= stack_bb:
            first = f"Er ligt een inzet van {bet_bb:g} big blinds; meegaan kost je je hele stack ({stack_bb:.0f} big blinds)."
        else:
            first = f"Er ligt een all-in van {bet_bb:g} big blinds; callen kost je die {bet_bb:g} van je {stack_bb:.0f} big blinds."
        lines = [
            first,
            "Een all-in callen vraagt een sterkere hand dan zelf duwen: de duwer heeft het initiatief en jij wint de "
            f"pot alleen door de beste hand te tonen. Voor een inzet van {effective_bb:.0f} big blinds call je ongeveer "
            f"de beste {share:.0%} van de handen ({allowed} van 169 handtypes); {label} staat op plaats {rank + 1}.",
        ]
        if go:
            lines.append(f"{label} valt daarbinnen: call. Je bent vaak favoriet of krijgt genoeg voor je chips.")
        else:
            lines.append(f"{label} valt erbuiten: fold. Liever wachten op een betere hand dan nu een muntje opgooien.")
        return PushFoldAdvice(go, "call" if go else "fold", share, rank, self.limit[label], tuple(lines))


NASH = NashPushFold()
