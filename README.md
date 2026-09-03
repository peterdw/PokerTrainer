# Poker Trainer

Leer **No-Limit Texas Hold'em** – de variant die op kampioenschappen zoals de
WSOP wordt gespeeld – spelenderwijs in de console. Het programma is geschreven
in Python 3.11+ zonder externe afhankelijkheden en is opgebouwd rond de
klassieke Gang-of-Four ontwerppatronen.

![De oefentafel in de browser: croupier, flop, coachadvies en actiebalk](docs/screenshot-tafel.png)

## Starten

Console:

```bash
python main.py
```

Browser (opent automatisch `http://127.0.0.1:8765/`; ook zonder externe pakketten):

```bash
python main.py --web
```

Opties: `--port 8080`, `--host 0.0.0.0`, `--no-browser`. Alternatief: `python -m pokertrainer.web`.

Tests draaien (pytest):

```bash
python -m pytest
```

## Wat je leert

| Menu | Les | Inhoud |
|------|-----|--------|
| 1 | Handrangschikking | Alle 10 categorieën met voorbeelden, daarna een quiz: "welke hand is dit?" en "wie wint de showdown?" |
| 2 | Regels van toernooipoker | In elf delen, vanaf nul: het kaartspel, chips en blinds, verloop van een hand, de acties, inzetregels, zijpotten, showdown, starthanden beoordelen (Chen-formule), toernooiregels en een woordenlijst. Met quiz. |
| 3 | Oefentafel met coach | 10 handen tegen drie bots met verschillende stijlen. De coach legt bij elke beslissing uit: starthandklasse, draws en outs, winkans, pot odds, positie en een advies. Wie bust is koopt opnieuw in. |
| 4 | Sit-and-go toernooi | Zes spelers, WSOP-achtige blindstructuur met big blind ante vanaf niveau 4. De coach helpt alleen als je `?` typt. |

Aan tafel typ je `f` (fold), `c` (call/check), `k` (check), `r 300` (bet/raise naar 300),
`a` (all-in), `?` (coach), `h` (hulp) of `q` (stoppen).

## Browserversie

Dezelfde vier lessen en exact dezelfde spelmotor, maar dan met een grafische
pokertafel: stoelen rond het laken, kaarten, chips, dealerbutton, pot, een
actiebalk met raise-slider en potpresets, een coachpaneel en een logboek.
De quizlessen tonen echte kaarten en geven meteen feedback; de regels staan
als bladzijden met een quiz erachter.

- Knoppen of sneltoetsen: `F` fold, `C` call/check, `K` check, `R` raise (bedrag
  van de slider), `A` all-in, `?` coach.
- Een gestileerde croupier deelt de kaarten: kaartruggen vliegen van haar hand naar elke stoel
  (twee rondes, zoals aan een echte tafel), naar het board en naar de burn-stapel; fiches schuiven
  na elke hand naar de winnaar. Wie `prefers-reduced-motion` aan heeft, ziet geen vliegende kaarten.
- De croupier praat mee in een tekstballon: "De flop: 6♠ 5♣ K♥", "Jij, aan u", "375 voor Rots",
  nieuwe blindniveaus, uitschakelingen en de winnaar. Met de knop **Stem** in de bovenbalk spreekt ze
  die zinnen ook hardop uit (spraaksynthese van de browser, Nederlandse stem indien aanwezig; standaard uit).
- Het tempo van de bots is instelbaar (schuif in de bovenbalk).
- Deeplink: `http://127.0.0.1:8765/?les=oefenen&naam=Peter` start meteen een les
  (`rangschikking`, `regels`, `oefenen` of `toernooi`).
- Aan de oefentafel adviseert de coach automatisch; in het toernooi alleen op verzoek.

De browserlaag (`pokertrainer/web/`) gebruikt alleen de standaardbibliotheek:
`http.server` levert de pagina en een kleine JSON-API, en het spelverloop komt
binnen via Server-Sent Events. De spelmotor draait per tafel in een
achtergrondthread; de mens antwoordt via een postvak (`queue.Queue`).

## Officiële regels die de motor afdwingt

- Blinds, dealerbutton die doorschuift, kaarten één voor één gedeeld, burn cards (de motor
  publiceert daarvoor een `CardBurned`-gebeurtenis).
- Een raise is minstens zo groot als de vorige bet of raise in dezelfde straat.
- Een all-in die kleiner is dan een volledige raise heropent de actie **niet**
  voor spelers die al gehandeld hebben (zij mogen alleen callen of folden).
- Big blind heeft preflop de optie; postflop begint de actie links van de button.
- Heads-up: de button is small blind, handelt preflop eerst en postflop laatst.
- Hoofdpot en zijpotten op basis van wat iedereen in totaal inzette; ongecald
  bedrag gaat terug; oneven chip naar de eerste speler links van de button.
- Showdown: de laatste agressor toont als eerste.
- Toernooi: stijgende blindniveaus, big blind ante, uitschakeling en rangschikking.

## Architectuur en patronen

```
main.py                      startpunt
pokertrainer/
  app.py         Facade          PokerTrainer: menu en samenstelling van alle onderdelen
  lessons.py     Template Method Lesson.run = intro → oefening → samenvatting
                 Factory Method  LessonFactory
  cards.py       Flyweight       52 gedeelde Card-instanties (Card.of), Deck als Iterator
  evaluation.py  Chain of Resp.  StraightFlushDetector → FourOfAKind → … → HighCard
  events.py      Observer        EventBus; ConsoleView, Coach en SessionStats abonneren zich
  actions.py     Command         Fold/Check/Call/Raise/AllIn-commando's + CommandFactory
  strategies.py  Strategy        HeuristicBotStrategy, HumanConsoleStrategy, ScriptedStrategy
  streets.py     State           PreFlop → Flop → Turn → River → Showdown
  tournament.py  Builder         TournamentConfigBuilder, presets (championship_sit_and_go)
  factory.py     Factory Method  PlayerFactory.create_strategy (bot- en mensfabriek)
  betting.py                     BettingRound: de inzetregels
  dealer.py                      HandRunner (één hand) en PotCalculator (zijpotten)
  session.py                     Tournament: reeks handen, niveaus, uitschakelingen
  coach.py                       Coach: uitleg en advies, gebaseerd op dezelfde strategie als de bots
  equity.py                      Monte-Carlo winkans
  view.py                        ConsoleView en SessionStats (observers)
  console.py                     UserIO-abstractie (ConsoleIO, ScriptedIO)
  quiz.py                        Quizvragen (gedeeld door console en browser)
  web/
    adapters.py  Adapter         WebIO en WebHumanStrategy: UserIO/DecisionStrategy voor de browser
                 Decorator       PacedStrategy: bedenktijd rond een botstrategie
    presenter.py Observer        TablePresenter: gebeurtenissen → JSON met momentopname van de tafel
    session.py                   WebSession: één tafel in een achtergrondthread, gebeurtenissenlog en postvak
    content.py                   Lesinhoud en quizvragen als JSON
    server.py    Facade          TrainerBackend + HTTP-server (JSON-API, Server-Sent Events, statische bestanden)
    static/                      index.html, style.css, app.js (vanilla JavaScript)
tests/                           pytest: evaluatie, inzetregels, zijpotten, toernooi, browserlaag
```

De spelmotor (dealer, betting, streets) kent geen console: hij publiceert
alleen gebeurtenissen. Daardoor is dezelfde motor bruikbaar voor de
oefentafel, het toernooi en de tests (die met `ScriptedStrategy` en
`ScriptedIO` werken).

## Bots

| Naam | Stijl |
|------|-------|
| Rots | tight-passief: speelt weinig handen, raiset zelden |
| Maniak | loose-agressief: speelt bijna alles en bet constant |
| Solide | tight-agressief: selectief, maar raiset met goede handen |
| Station | calling station: callt veel, raiset bijna nooit |
| Prof | solide en agressief, let op pot odds |

Alle bots gebruiken dezelfde `HeuristicBotStrategy` met een ander profiel
(`looseness`, `aggression`): preflop op basis van de Chen-formule, postflop
op basis van geschatte winkans versus pot odds.

## Licentie

MIT, zie [LICENSE](LICENSE).
