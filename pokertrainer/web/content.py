"""Lesinhoud als JSON voor de browser.

Alles komt uit dezelfde bron als de consoleles (``lessons``, ``quiz``,
``factory``, ``tournament``), zodat beide versies nooit uit de pas lopen.
"""

from __future__ import annotations

from ..cards import parse_cards
from ..evaluation import HandCategory
from ..factory import BOT_PROFILES
from ..lessons import RULE_PAGES, RULE_QUIZ, LessonFactory, PracticeLesson, TournamentLesson
from ..push_fold import NASH, PushFoldAdvice
from ..quiz import EXAMPLE_HANDS, QuizGenerator
from ..starting_hands import CHART_POSITIONS, HAND_MODELS, HandAssessment, hand_model, label_cards, normalize_label
from ..tournament import championship_sit_and_go, practice_table
from .presenter import cards_json, level_json

LESSON_META: dict[str, dict[str, str]] = {
    "rangschikking": {
        "icon": "🃏",
        "kind": "ranking",
        "description": "Alle tien handcategorieën met voorbeelden. Daarna een quiz: welke hand is dit, "
        "en wie wint de showdown?",
    },
    "regels": {
        "icon": "📜",
        "kind": "rules",
        "description": "Vanaf nul uitgelegd: het kaartspel, chips en blinds, het verloop van een hand, "
        "wat je in je beurt kunt doen, zijpotten, de showdown en de toernooiregels. Met quiz.",
    },
    "oefenen": {
        "icon": "🎓",
        "kind": "table",
        "description": "Tien handen tegen drie bots met elk hun eigen stijl. De coach legt bij elke "
        "beslissing uit wat hij zou doen en waarom.",
    },
    "toernooi": {
        "icon": "🏆",
        "kind": "table",
        "description": "Zes spelers, een WSOP-achtige blindstructuur met big blind ante. De coach helpt "
        "alleen als je erom vraagt.",
    },
}


def _table_json(lesson: type[PracticeLesson] | type[TournamentLesson], config) -> dict:
    return {
        "title": lesson.title,
        "bots": [BOT_PROFILES[key].name for key in lesson.bot_keys],
        "auto_advice": lesson.auto_advice,
        "max_hands": lesson.max_hands,
        "starting_stack": config.starting_stack,
        "hands_per_level": config.hands_per_level,
        "rebuys": config.rebuys,
        "big_blind_ante": config.big_blind_ante,
        "levels": [level_json(level) for level in config.levels],
    }


COACH_LOOSENESS = 0.45  # dezelfde speelstijl als de coach


def models_json(default_key: str) -> dict:
    return {
        "default": default_key,
        "models": [
            {"key": model.key, "name": model.name, "description": model.description} for model in HAND_MODELS.values()
        ],
    }


def positions_json() -> list[dict]:
    return [{"key": position, "name": position} for position, _ in CHART_POSITIONS] + [
        {"key": "big blind", "name": "big blind"}
    ]


def assessment_json(assessment: HandAssessment, situation: str = "open") -> dict:
    """Oordeel plus het advies in één woord, met dezelfde drempels als de bot."""
    if assessment.premium:
        advice = "re-raise" if situation == "raise" else "raise"
    elif situation == "raise":
        advice = "call" if assessment.worth_a_call else "fold"
    else:
        advice = "speelbaar" if assessment.playable else "fold"
    return {
        "label": assessment.label,
        "verdict": assessment.verdict,
        "advice": advice,
        "fold": advice == "fold",
        "value": round(assessment.value, 3),
        "strength": round(assessment.strength, 3),
        "playable": assessment.playable,
        "premium": assessment.premium,
        "lines": list(assessment.lines),
    }


SITUATIONS = {
    "open": "niemand heeft geraised",
    "raise": "er is al geraised",
    "push": "korte stack: zelf all-in?",
    "call": "korte stack: een all-in callen?",
}


def _push_json(advice: PushFoldAdvice) -> dict:
    return {
        "key": "push-or-fold",
        "name": "Push-or-fold-tabel (Nash-benadering)",
        "verdict": advice.action,
        "advice": advice.action,
        "fold": not advice.go,
        "value": None,
        "strength": None,
        "playable": advice.go,
        "premium": False,
        "lines": list(advice.lines),
    }


def starting_hand_json(hand: str, position: str, situation: str = "open", stack: float = 8.0, behind: int = 1) -> dict:
    """Het oordeel over één starthand in een situatie; ValueError bij onbekende invoer."""
    label = normalize_label(hand)
    if position not in {key["key"] for key in positions_json()}:
        raise ValueError(f"Onbekende positie: {position!r}")
    if situation not in SITUATIONS:
        raise ValueError(f"Onbekende situatie: {situation!r}")
    stack = min(max(float(stack), 1.0), 30.0)
    behind = min(max(int(behind), 0), 9)
    if situation == "push":
        models = [_push_json(NASH.pushing(label_cards(label), stack, position, behind, COACH_LOOSENESS))]
    elif situation == "call":
        models = [_push_json(NASH.calling(label_cards(label), stack, looseness=COACH_LOOSENESS))]
    else:
        models = []
        for model in HAND_MODELS.values():
            method = model.defend_label if situation == "raise" else model.assess_label
            assessment = method(label, position, COACH_LOOSENESS)
            models.append({"key": model.key, "name": model.name, **assessment_json(assessment, situation)})
    return {"hand": label, "position": position, "situation": situation, "stack": stack, "behind": behind, "models": models}


def build_content(default_model: str = "beginner") -> dict:
    lessons = []
    for key in LessonFactory.keys():
        meta = LESSON_META.get(key, {"icon": "•", "kind": "unknown", "description": ""})
        lessons.append({"key": key, "title": LessonFactory.title(key), **meta})

    categories = [
        {
            "key": category.name,
            "rank": number,
            "name": category.dutch_name,
            "explanation": category.explanation,
            "example": cards_json(parse_cards(EXAMPLE_HANDS[category])),
        }
        for number, category in enumerate(reversed(list(HandCategory)), start=1)
    ]
    rules = {
        "pages": [{"heading": heading, "lines": list(lines)} for heading, lines in RULE_PAGES],
        "quiz": [
            {"question": question, "options": list(options), "correct": correct, "explanation": explanation}
            for question, options, correct, explanation in RULE_QUIZ
        ],
    }
    bots = [
        {
            "key": key,
            "name": profile.name,
            "description": profile.description,
            "looseness": profile.looseness,
            "aggression": profile.aggression,
        }
        for key, profile in BOT_PROFILES.items()
    ]
    tables = {
        PracticeLesson.key: _table_json(PracticeLesson, practice_table()),
        TournamentLesson.key: _table_json(TournamentLesson, championship_sit_and_go()),
    }
    return {
        "lessons": lessons,
        "ranking": {"categories": categories},
        "rules": rules,
        "bots": bots,
        "tables": tables,
        "coach": models_json(hand_model(default_model).key),
        "positions": positions_json(),
        "situations": [{"key": key, "name": name} for key, name in SITUATIONS.items()],
    }


def ranking_quiz_json(generator: QuizGenerator, questions: int = 6, showdowns: int = 4) -> dict:
    return {
        "questions": [
            {
                "cards": cards_json(question.cards),
                "category": question.value.category.name,
                "answer": question.value.describe(),
                "best_five": cards_json(question.value.best_five),
            }
            for question in generator.ranking_questions(questions)
        ],
        "showdowns": [
            {
                "board": cards_json(question.board),
                "hand_a": cards_json(question.hand_a),
                "hand_b": cards_json(question.hand_b),
                "correct": question.correct,
                "describe_a": question.value_a.describe(),
                "describe_b": question.value_b.describe(),
                "best_a": cards_json(question.value_a.best_five),
                "best_b": cards_json(question.value_b.best_five),
            }
            for question in (generator.showdown_question() for _ in range(showdowns))
        ],
    }
