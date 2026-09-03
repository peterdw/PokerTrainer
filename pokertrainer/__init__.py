"""Poker Trainer - leer No-Limit Texas Hold'em zoals het in kampioenschappen wordt gespeeld.

Pakketoverzicht (met de gebruikte Gang-of-Four patronen):

- cards        : Card (Flyweight), Deck (Iterator)
- evaluation   : HandEvaluator (Chain of Responsibility)
- events       : EventBus (Observer)
- actions      : Action-commando's (Command)
- strategies   : Beslisstrategieen voor bots en mens (Strategy)
- streets      : Straten van een hand: preflop/flop/turn/river/showdown (State)
- dealer       : HandRunner en Pot-verdeling
- tournament   : TournamentConfig (Builder), BotFactory (Factory Method)
- lessons      : Lesson (Template Method), LessonFactory (Factory Method)
- coach        : Coach die advies geeft (Observer + Facade op de evaluator)
- app          : PokerTrainer (Facade) met het hoofdmenu
"""

__version__ = "1.0.0"
