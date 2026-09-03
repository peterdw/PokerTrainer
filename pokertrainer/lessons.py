"""Lessen: van handrangschikking tot een volledig toernooi.

Patroon: Template Method. ``Lesson.run`` legt het vaste verloop vast
(intro -> oefening -> samenvatting); elke les vult alleen de stappen in.
Patroon: Factory Method. ``LessonFactory`` maakt lessen op basis van een sleutel.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .cards import cards_to_str, parse_cards
from .coach import Coach
from .console import QuitRequested, UserIO
from .equity import EquityCalculator
from .evaluation import HandCategory, HandEvaluator
from .events import EventBus
from .factory import HumanPlayerFactory, create_bot_lineup
from .quiz import EXAMPLE_HANDS, QuizGenerator
from .rules_content import RULE_PAGES, RULE_QUIZ
from .session import Tournament
from .tournament import TournamentConfig, championship_sit_and_go, practice_table
from .view import ConsoleView, SessionStats


@dataclass
class TrainerServices:
    io: UserIO
    rng: random.Random
    evaluator: HandEvaluator
    equity: EquityCalculator
    player_name: str


class Lesson(ABC):
    key: str = ""
    title: str = ""

    def __init__(self, services: TrainerServices) -> None:
        self._services = services
        self._io = services.io

    def run(self) -> None:
        """Template Method: het vaste verloop van elke les."""
        self._io.show("")
        self._io.show(f"╔══ Les: {self.title} " + "═" * max(0, 50 - len(self.title)))
        self.intro()
        try:
            self.exercise()
        except QuitRequested:
            self._io.show("Je hebt de oefening verlaten.")
        self.summary()

    @abstractmethod
    def intro(self) -> None: ...

    @abstractmethod
    def exercise(self) -> None: ...

    def summary(self) -> None:
        self._io.show("Einde van de les. Terug naar het menu.")

    # --- hulpmiddelen -------------------------------------------------------
    def _pause(self) -> None:
        if self._io.ask("[Enter] om verder te gaan, [q] om te stoppen: ").strip().lower() == "q":
            raise QuitRequested()

    def _ask_choice(self, prompt: str, valid: range) -> int:
        while True:
            raw = self._io.ask(prompt).strip().lower()
            if raw == "q":
                raise QuitRequested()
            if raw.isdigit() and int(raw) in valid:
                return int(raw)
            self._io.show(f"Kies een getal van {valid.start} tot {valid.stop - 1}.")


# --- Les 1: handrangschikking -----------------------------------------------
class HandRankingLesson(Lesson):
    key = "rangschikking"
    title = "Handrangschikking"

    def intro(self) -> None:
        self._io.show("In Texas Hold'em maak je de beste hand van 5 kaarten uit je 2 eigen kaarten")
        self._io.show("en de 5 gemeenschappelijke kaarten (het board). Van sterk naar zwak:")
        self._io.show("")
        for number, category in enumerate(reversed(list(HandCategory)), start=1):
            cards = cards_to_str(parse_cards(EXAMPLE_HANDS[category]))
            self._io.show(f" {number:>2}. {category.dutch_name:<28} {cards:<18} {category.explanation}")
        self._io.show("")
        self._io.show("Bij gelijke categorie beslist de hoogste kaart (kicker); bij volledig gelijke handen")
        self._io.show("wordt de pot gedeeld. Kleuren (♠♥♦♣) zijn nooit hoger dan elkaar.")
        self._pause()

    def exercise(self) -> None:
        self._io.show("Oefening 1: welke hand is dit? (7 kaarten, kies de beste combinatie van 5)")
        categories = list(reversed(list(HandCategory)))
        generator = QuizGenerator(self._services.rng, self._services.evaluator)
        score = 0
        questions = 6
        for number, question in enumerate(generator.ranking_questions(questions), start=1):
            value = question.value
            self._io.show("")
            self._io.show(f"Vraag {number}: {cards_to_str(question.cards)}")
            for index, category in enumerate(categories, start=1):
                self._io.show(f"   {index:>2}. {category.dutch_name}")
            answer = self._ask_choice("Jouw antwoord: ", range(1, len(categories) + 1))
            if categories[answer - 1] is value.category:
                score += 1
                self._io.show(f"✔ Juist! {value.describe()} ({cards_to_str(value.best_five)})")
            else:
                self._io.show(f"✘ Nee. Het is: {value.describe()} ({cards_to_str(value.best_five)})")
        self._io.show(f"Score: {score}/{questions}")
        self._pause()

        self._io.show("Oefening 2: wie wint bij de showdown?")
        score = 0
        questions = 4
        for number in range(1, questions + 1):
            question = generator.showdown_question()
            self._io.show("")
            self._io.show(f"Vraag {number}: board {cards_to_str(question.board)}")
            self._io.show(f"   1. Speler A: {cards_to_str(question.hand_a)}")
            self._io.show(f"   2. Speler B: {cards_to_str(question.hand_b)}")
            self._io.show("   3. Gedeelde pot")
            answer = self._ask_choice("Jouw antwoord: ", range(1, 4))
            if answer == question.correct:
                score += 1
                self._io.show("✔ Juist!")
            else:
                self._io.show("✘ Nee.")
            self._io.show(f"   A: {question.value_a.describe()}   |   B: {question.value_b.describe()}")
        self._io.show(f"Score: {score}/{questions}")


# --- Les 2: regels van het toernooipoker ------------------------------------
class RulesLesson(Lesson):
    key = "regels"
    title = "Regels van toernooipoker (No-Limit Texas Hold'em)"

    def intro(self) -> None:
        self._io.show("Op kampioenschappen zoals de WSOP wordt No-Limit Texas Hold'em gespeeld.")
        self._io.show("No-limit betekent: je mag op elk moment alles inzetten wat je voor je hebt.")
        self._io.show("Deze les begint bij het begin: het kaartspel, de chips en de verplichte inzetten.")
        self._io.show(f"Daarna volgen het verloop van een hand, de acties en de toernooiregels ({len(RULE_PAGES)} delen).")
        for number, (heading, lines) in enumerate(RULE_PAGES, start=1):
            self._io.show("")
            self._io.show(f"── Deel {number}/{len(RULE_PAGES)}: {heading} ──")
            for line in lines:
                self._io.show(line)
            self._pause()

    def exercise(self) -> None:
        self._io.show("Korte quiz over de regels:")
        score = 0
        for number, (question, options, correct, explanation) in enumerate(RULE_QUIZ, start=1):
            self._io.show("")
            self._io.show(f"Vraag {number}: {question}")
            for index, option in enumerate(options, start=1):
                self._io.show(f"   {index}. {option}")
            answer = self._ask_choice("Jouw antwoord: ", range(1, len(options) + 1))
            if answer == correct:
                score += 1
                self._io.show("✔ Juist! " + explanation)
            else:
                self._io.show(f"✘ Nee, het juiste antwoord is {correct}. " + explanation)
        self._io.show(f"Score: {score}/{len(RULE_QUIZ)}")


# --- Les 3 en 4: spelen ------------------------------------------------------
class _PlayLesson(Lesson):
    bot_keys: list[str] = []
    auto_advice = False
    max_hands: int | None = None

    def __init__(self, services: TrainerServices) -> None:
        super().__init__(services)
        self._stats = SessionStats(services.player_name)

    @abstractmethod
    def config(self) -> TournamentConfig: ...

    def exercise(self) -> None:
        services = self._services
        config = self.config()
        bus = EventBus()
        coach = Coach(services.evaluator, services.equity, self._io, services.player_name, services.rng)
        human = HumanPlayerFactory(self._io, coach, self.auto_advice).create(
            services.player_name, config.starting_stack
        )
        bots = create_bot_lineup(self.bot_keys, config.starting_stack, services.evaluator, services.rng)
        players = [human, *bots]
        services.rng.shuffle(players)
        bus.subscribe(ConsoleView(self._io, services.player_name))
        bus.subscribe(coach)
        bus.subscribe(self._stats)
        tournament = Tournament(config, players, bus, services.evaluator, services.rng)
        tournament.run(self.max_hands)
        if human.chips > 0 and tournament.ranking[:1] != [human]:
            self._io.show("")
            self._io.show(f"Je stopt met {human.chips} chips.")

    def summary(self) -> None:
        self._io.show("")
        self._io.show(self._stats.summary())
        super().summary()


class PracticeLesson(_PlayLesson):
    key = "oefenen"
    title = "Oefentafel met coach"
    bot_keys = ["rots", "maniak", "solide"]
    auto_advice = True
    max_hands = 10

    def config(self) -> TournamentConfig:
        return practice_table()

    def intro(self) -> None:
        self._io.show("Je speelt 10 handen tegen drie bots met verschillende stijlen:")
        self._io.show("  Rots (tight-passief), Maniak (loose-agressief) en Solide (tight-agressief).")
        self._io.show("De coach legt bij elke beslissing uit wat hij zou doen en waarom.")
        self._io.show("Je hoeft het advies niet te volgen: proberen en fouten maken is de bedoeling.")
        self._io.show("Wie zonder chips valt, koopt automatisch opnieuw in.")
        self._io.show("Typ [h] voor de mogelijke acties, [q] om te stoppen.")
        self._pause()


class TournamentLesson(_PlayLesson):
    key = "toernooi"
    title = "Sit-and-go toernooi (kampioenschapsstructuur)"
    bot_keys = ["rots", "maniak", "solide", "station", "prof"]
    auto_advice = False

    def config(self) -> TournamentConfig:
        return championship_sit_and_go()

    def intro(self) -> None:
        config = self.config()
        self._io.show(f"Zes spelers, {config.starting_stack} chips elk. De blinds stijgen elke "
                      f"{config.hands_per_level} handen:")
        self._io.show("  " + ", ".join(str(level) for level in config.levels[:6]) + ", ...")
        self._io.show("Vanaf niveau 4 betaalt de big blind een big blind ante, zoals op de WSOP.")
        self._io.show("De coach zwijgt nu, tenzij je [?] typt. Wie als laatste overblijft wint.")
        self._pause()


class LessonFactory:
    _lessons: dict[str, type[Lesson]] = {
        HandRankingLesson.key: HandRankingLesson,
        RulesLesson.key: RulesLesson,
        PracticeLesson.key: PracticeLesson,
        TournamentLesson.key: TournamentLesson,
    }

    @classmethod
    def keys(cls) -> list[str]:
        return list(cls._lessons)

    @classmethod
    def title(cls, key: str) -> str:
        return cls._lessons[key].title

    @classmethod
    def create(cls, key: str, services: TrainerServices) -> Lesson:
        try:
            return cls._lessons[key](services)
        except KeyError as error:
            raise ValueError(f"Onbekende les: {key}") from error
