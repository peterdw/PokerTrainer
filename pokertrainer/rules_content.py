"""De lesstof van les 2: de regels van toernooipoker, uitgelegd vanaf nul.

Geschreven voor iemand die nog nooit een kaartspel heeft gespeeld. De console
toont de regels letterlijk; de browser maakt er opsommingen en definities van.
Afspraken in de tekst:
- ``1. ...`` en ``• ...``      opsommingen
- ``TERM : uitleg``           definitie van een begrip (term in hoofdletters)
- regel die met spaties begint  hoort bij de regel erboven (vervolgregel)
- ``Voorbeeld: ...``          een rekenvoorbeeld
"""

from .push_fold import NASH, PUSH_FOLD_LIMIT
from .starting_hands import HAND_MODELS, RangeChartModel

_CHART = HAND_MODELS[RangeChartModel.key]
assert isinstance(_CHART, RangeChartModel)


def _push_examples() -> str:
    def text(label: str) -> str:
        limit = NASH.limit[label]
        return f"{label} altijd" if limit >= 20 else f"{label} tot {limit:g}".replace(".", ",")

    return ", ".join(text(label) for label in ("A2o", "22", "K5o", "Q7o", "76s", "72o")) + " big blinds."


def _push_shares() -> list[str]:
    return [
        f"  ± {NASH.push_share(10, 5, 'vroeg (under the gun)'):.0%} onder de gun (vijf kunnen callen), "
        f"± {NASH.push_share(10, 2, 'button'):.0%} op de button (twee kunnen callen),",
        f"  ± {NASH.push_share(10, 1, 'small blind'):.0%} heads-up in de small blind (alleen de big blind kan callen).",
    ]

RULE_PAGES: list[tuple[str, list[str]]] = [
    (
        "Waar gaat het om?",
        [
            "Poker speel je met chips: fiches die je inzet. In deze trainer zijn ze gratis; in een echt",
            "toernooi koopt iedereen voor hetzelfde bedrag dezelfde stapel chips. Die stapel heet je 'stack'.",
            "Het spel bestaat uit een reeks losse rondes. Zo'n ronde heet een 'hand'. In elke hand ontstaat",
            "een 'pot': alle chips die de spelers in die hand inzetten. Wie de hand wint, krijgt de hele pot.",
            "Een hand win je op twee manieren:",
            "1. Alle andere spelers geven op ('passen' of 'folden'). De pot is dan voor jou, zonder dat je",
            "   je kaarten hoeft te laten zien.",
            "2. Er blijven twee of meer spelers over en jij hebt bij het vergelijken van de kaarten",
            "   (de 'showdown') de sterkste combinatie.",
            "Doel van een toernooi: als laatste overblijven met álle chips. Wie zonder chips zit, ligt eruit.",
            "Poker is dus geen spel van 'wie de mooiste kaarten krijgt', maar van slim inzetten: goede kaarten",
            "laten betalen, en met slechte kaarten zo weinig mogelijk verliezen.",
        ],
    ),
    (
        "Het kaartspel",
        [
            "We spelen met één gewoon spel van 52 kaarten, zonder jokers.",
            "Elke kaart heeft een kleur (de soort) en een waarde.",
            "• De vier kleuren: schoppen ♠, harten ♥, ruiten ♦ en klaveren ♣. Geen enkele kleur is meer waard",
            "  dan een andere: een schoppen aas en een harten aas zijn precies even sterk.",
            "• De dertien waarden, van laag naar hoog: 2, 3, 4, 5, 6, 7, 8, 9, 10, boer (J), vrouw (Q),",
            "  heer (K) en aas (A). De aas is de hoogste kaart, maar mag in één combinatie ook als 1 tellen.",
            "In dit programma schrijven we een kaart kort als waarde + kleur: A♠ is de schoppen aas, T♥ de",
            "harten tien (T van 'ten'), J♦ de ruiten boer, 7♣ de klaveren zeven.",
            "Bij poker draait alles om combinaties van vijf kaarten. Twee kaarten met dezelfde waarde heten",
            "'een paar', vijf kaarten van dezelfde kleur een 'flush', vijf opeenvolgende waarden een 'straight'.",
            "Les 1 (Handrangschikking) toont alle tien combinaties met voorbeelden en oefent ze met een quiz.",
        ],
    ),
    (
        "De tafel: chips, dealerbutton en blinds",
        [
            "Aan een tafel zitten 2 tot 10 spelers. Iedereen heeft zijn eigen stapel chips (stack) voor zich.",
            "DEALERBUTTON : een schijf met een D die aangeeft wie deze hand de 'dealer' is. Na elke hand",
            "  schuift de button één plaats met de klok mee, zodat iedereen om de beurt elke plaats krijgt.",
            "Zonder verplichte inzet zou iedereen kunnen wachten op perfecte kaarten. Daarom zetten twee",
            "spelers vóór het delen 'blind' in, dus zonder hun kaarten te kennen:",
            "SMALL BLIND : de speler links van de button zet een klein vast bedrag, bijvoorbeeld 25.",
            "BIG BLIND : de speler daarnaast zet het dubbele, bijvoorbeeld 50. Dit is de basisinzet van de hand.",
            "ANTE : in latere fasen van een toernooi komt er nog een extra verplichte inzet bij (zie verderop).",
            "De blinds tellen gewoon mee als inzet van die spelers. 'Blinds 25/50' betekent dus: small blind 25,",
            "big blind 50. Zo ligt er meteen iets in de pot om voor te spelen.",
        ],
    ),
    (
        "Het verloop van een hand",
        [
            "1. De button schuift door; small blind en big blind gaan in de pot.",
            "2. Iedereen krijgt twee dichte kaarten, de 'hole cards'. Alleen jij ziet die van jou.",
            "3. Eerste inzetronde, de PREFLOP. De speler links van de big blind begint ('under the gun').",
            "4. De FLOP: drie open kaarten in het midden van de tafel. Die zijn van iedereen (het 'board').",
            "   Tweede inzetronde, nu te beginnen bij de eerste speler links van de button.",
            "5. De TURN: een vierde open kaart. Derde inzetronde.",
            "6. De RIVER: de vijfde en laatste open kaart. Vierde en laatste inzetronde.",
            "7. De SHOWDOWN: wie nog meedoet, toont zijn kaarten. Je maakt de best mogelijke combinatie van",
            "   vijf kaarten uit je twee eigen kaarten plus de vijf op tafel. De beste combinatie wint de pot.",
            "Zodra in een inzetronde iedereen op één speler na past, stopt de hand meteen: die speler krijgt",
            "de pot. Vóór flop, turn en river legt de dealer eerst één kaart blind weg (de 'burn card'),",
            "zodat niemand iets heeft aan een per ongeluk geziene bovenste kaart.",
        ],
    ),
    (
        "Jouw beurt: wat kun je doen?",
        [
            "Als jij aan de beurt bent, kijk je eerst of iemand vóór jou in deze ronde al heeft ingezet.",
            "Heeft nog niemand ingezet, dan kun je kiezen uit:",
            "CHECK : niets inzetten en de beurt doorgeven. Gratis; je blijft gewoon meedoen.",
            "BET : als eerste chips inzetten. Minimaal één big blind.",
            "Heeft iemand wél ingezet, dan moet je kiezen uit:",
            "FOLD : passen. Je legt je kaarten weg, doet deze hand niet meer mee en bent kwijt wat je al inzette.",
            "CALL : evenveel bijleggen als de hoogste inzet tot nu toe, zodat je mee blijft doen.",
            "RAISE : de inzet verhogen. De anderen moeten dan opnieuw kiezen: folden, callen of nog eens raisen.",
            "En altijd mogelijk:",
            "ALL-IN : al je chips inzetten. Je kunt nooit meer verliezen dan wat je voor je hebt ('table stakes').",
            "Voorbeeld: blinds 25/50, speler A raiset naar 150 en jij hebt nog niets ingezet. Callen kost je",
            "150, passen kost niets extra, en een raise moet minstens naar 250 (zie de inzetregels).",
            "Tip: als checken kan, is folden nooit nodig. Dit programma checkt dan automatisch voor je.",
        ],
    ),
    (
        "De inzetregels",
        [
            "• Een inzetronde eindigt als iedereen die nog meedoet evenveel heeft ingezet (of all-in is)",
            "  en iedereen minstens één keer aan de beurt is geweest.",
            "• Een bet is minimaal één big blind.",
            "• Een raise is minstens zo groot als de vorige bet of raise in dezelfde ronde.",
            "  Voorbeeld: blinds 50/100. Iemand raiset naar 300; dat is een verhoging van 200 bovenop de 100.",
            "  Wil jij opnieuw raisen, dan moet dat minstens naar 500 (300 + 200).",
            "• All-in mag altijd, ook als het minder is dan een volledige raise. Zo'n 'korte' all-in heropent",
            "  de actie niet: wie al gehandeld heeft, mag daarna alleen nog callen of folden.",
            "• De big blind heeft preflop de 'optie': heeft niemand geraised, dan mag hij checken of raisen.",
            "• Postflop begint elke ronde bij de eerste speler links van de button; de button is dus als",
            "  laatste aan de beurt en ziet eerst wat de anderen doen. Dat is een groot voordeel.",
            "• Een ongeldige zet wordt in dit programma geweigerd met uitleg; je kiest dan gewoon opnieuw.",
        ],
    ),
    (
        "All-in en zijpotten",
        [
            "Je kunt van een tegenstander nooit meer winnen dan je zelf hebt ingezet. Daarom ontstaan er",
            "soms meerdere potten als iemand all-in gaat voor minder dan de anderen inzetten.",
            "Voorbeeld: speler A heeft 500 chips en gaat all-in. B en C hebben er 2000 en callen allebei.",
            "De hoofdpot is 3 x 500 = 1500; daar maakt iedereen kans op, ook A.",
            "Zetten B en C daarna nog meer in, dan gaat dat in een zijpot waar alleen B en C om spelen.",
            "Wint A de showdown, dan krijgt A de hoofdpot en gaat de zijpot naar de beste van B en C.",
            "• Een inzet die niemand callt, gaat terug naar wie hem deed.",
            "• Bij een gedeelde pot gaat een eventuele oneven chip naar de eerste speler links van de button.",
            "• Bij de showdown toont de laatste 'agressor' (wie het laatst bette of raisete) als eerste.",
        ],
    ),
    (
        "Wie wint? De showdown",
        [
            "Bij de showdown telt voor iedereen de beste combinatie van vijf kaarten uit zeven: je twee",
            "eigen kaarten plus de vijf op tafel. Je mag daarbij ook maar één of zelfs geen eigen kaart gebruiken.",
            "De volgorde van sterk naar zwak (les 1 toont voorbeelden):",
            "1. Royal flush  2. Straight flush  3. Four of a kind  4. Full house  5. Flush",
            "6. Straight  7. Three of a kind  8. Twee paar  9. Een paar  10. Hoge kaart",
            "• Hebben twee spelers dezelfde soort combinatie, dan beslist de hoogste kaart erin, en daarna de",
            "  'kicker': de hoogste overgebleven kaart. Voorbeeld: A-A-K-7-3 wint van A-A-Q-9-5.",
            "• Zijn de vijf kaarten precies even hoog, dan wordt de pot gedeeld. Kleuren tellen nooit mee.",
            "• Wie ziet dat hij verloren heeft, mag zijn kaarten weggooien zonder ze te tonen ('mucken').",
        ],
    ),
    (
        "Starthanden beoordelen",
        [
            "De coach beoordeelt je twee eigen kaarten met de Chen-formule, een klassieke rekenregel.",
            "Eerst de notatie die je bij de coach ziet:",
            "• Achter de twee waarden staat een letter: 'o' (offsuit) als de kleuren verschillen, 's' (suited)",
            "  als ze gelijk zijn. K5o is een heer en een vijf van verschillende kleur; QQ is een paar vrouwen.",
            "Zo tel je de punten:",
            "1. Hoogste kaart: aas 10, heer 8, vrouw 7, boer 6; lagere kaarten de helft van hun waarde (tien 5).",
            "2. Een paar: verdubbel die punten (minimaal 5). Zo is 99 negen punten waard en 22 vijf.",
            "3. Suited: 2 punten erbij.",
            "4. Het gat tussen de twee waarden: geen kaart ertussen 0, één kaart -1, twee -2, drie -4, meer -5.",
            "5. Twee aansluitende kaarten (gat 0 of 1) lager dan de vrouw: 1 punt erbij, want die maken",
            "   makkelijk straights.",
            "6. Rond naar boven af. Klasse: 12 of meer premium, 9 tot 11 sterk, 7 of 8 speelbaar, 5 of 6 marginaal,",
            "   minder dan 5 zwak.",
            "Voorbeeld: K5o = heer 8, gat van zeven kaarten -5 = 3: zwak. AKs = aas 10, suited +2 = 12: premium.",
            "Vuistregels zonder rekenen:",
            "• Elk paar is speelbaar; 99 en hoger is sterk, JJ en hoger premium.",
            "• Twee plaatjes of tienen bij elkaar ('broadways') zijn speelbaar tot sterk.",
            "• Hoe groter het gat, hoe slechter. Een heer of aas met een lage kaart is een klassieke beginnersval.",
            "• Suited is een bonus van ongeveer één klasse, maar redt geen slechte hand.",
            "• Aansluitend én suited (76s, 98s) is speelbaar, vooral in late positie tegen veel spelers.",
            "• Positie telt mee: de coach geeft in late positie 1 punt extra.",
            "De Chen-formule is de coachmethode 'beginner'. De methode 'gevorderd' rekent niet, maar gebruikt",
            "een rangetabel per positie, zoals spelers het in de praktijk leren: hoe later je positie, hoe meer",
            "handen je opent.",
            *_CHART.summary_lines(),
            "De big blind verdedigt even ruim als de button, want hij heeft al geld in de pot. Buiten de tabel",
            "voor jouw positie is het antwoord fold, hoe mooi de hand er ook uitziet. Wisselen van methode kan in",
            "het menu (console) of op het startscherm (browser).",
        ],
    ),
    (
        "Verdedigen tegen een raise en push-or-fold",
        [
            "Als er vóór jou al geraised is, gelden andere regels dan om zelf te openen. De raiser heeft een sterke",
            "hand aangekondigd en het initiatief; jij betaalt om mee te mogen doen. De rangetabel (methode",
            "'gevorderd') kent daarvoor aparte verdedigingsranges:",
            *_CHART.defend_summary_lines(),
            f"Korte stack (minder dan ± {PUSH_FOLD_LIMIT:.0f} big blinds): push-or-fold, met beide coachmethodes.",
            "• Een gewone raise heeft dan geen zin: na een call zit je vast aan de pot en kun je niet meer folden.",
            "  Je gaat all-in of je past, niets ertussen.",
            "• De push-or-fold-tabel (een vereenvoudiging van de wiskundig beste strategie voor twee spelers, de",
            "  'Nash-tabel') zegt tot hoeveel big blinds je met een hand all-in gaat ('duwt'):",
            "  " + _push_examples(),
            "• Hoe meer tegenstanders je all-in nog kunnen callen, hoe minder handen je duwt: elke extra speler is",
            "  een extra kans dat iemand een sterkere hand heeft. Bij 10 big blinds:",
            *_push_shares(),
            "• Ligt er al een raise van een grotere stack, dan ga je er all-in overheen ('re-shove') of je past;",
            "  callen kan niet met zo'n korte stack. Dat vraagt meer dan zelf duwen: de raiser toonde al kracht.",
            "• Een all-in callen vraagt het meest: de duwer heeft het initiatief en jij wint alleen met de beste",
            f"  hand. Bij 10 big blinds call je ongeveer de beste {NASH.call_share(10):.0%} van de handen.",
            "De coach noemt bij elke beslissing de regel die hij toepast én waarom, zodat je het advies kunt toetsen",
            "in plaats van blind volgen. In de browser kun je in het vorige deel elke situatie zelf naspelen.",
        ],
    ),
    (
        "Toernooiregels (zoals op de WSOP)",
        [
            "• Iedereen start met evenveel chips. Wie geen chips meer heeft, is uitgeschakeld.",
            "• De blinds stijgen volgens een vast schema (niveaus), bijvoorbeeld elke 8 handen of elke",
            "  20 minuten. Zo wordt afwachten steeds duurder en komt er vanzelf actie.",
            "• Vanaf een bepaald niveau komt er een ANTE bij. In moderne toernooien betaalt de big blind één",
            "  'big blind ante' voor de hele tafel, zodat het delen snel blijft gaan.",
            "• Heads-up (nog twee spelers): de button is dan ook small blind, handelt preflop als eerste",
            "  en na de flop als laatste.",
            "• De laatste speler met alle chips wint. De eindstand volgt de volgorde van uitschakelen.",
            f"• Strategietip: met minder dan ± {PUSH_FOLD_LIMIT:.0f} big blinds speel je 'push or fold': all-in of",
            "  passen, want voor een gewone raise en een fold daarna heb je te weinig chips (zie het vorige deel).",
        ],
    ),
    (
        "Posities en woordenlijst",
        [
            "Je plaats ten opzichte van de button bepaalt wanneer je aan de beurt bent. Later aan de beurt zijn",
            "is een voordeel: je ziet eerst wat de anderen doen. De coach gebruikt deze namen:",
            "UNDER THE GUN : de eerste speler links van de big blind; handelt preflop als eerste ('vroeg').",
            "MIDDEN : de plaatsen daarna.",
            "CUTOFF : de plaats rechts van de button ('laat').",
            "BUTTON : handelt na de flop altijd als laatste: de beste plaats aan tafel.",
            "Andere woorden die je aan tafel tegenkomt:",
            "STACK : je eigen stapel chips.",
            "POT : alle chips die in deze hand zijn ingezet.",
            "BOARD : de open kaarten in het midden van de tafel.",
            "STRAAT : een inzetronde: preflop, flop, turn of river.",
            "OUTS : kaarten die jouw hand nog kunnen verbeteren tot een waarschijnlijke winnaar.",
            "WINKANS : de kans dat jij de hand wint, geschat door de coach.",
            "POT ODDS : wat je moet bijleggen vergeleken met wat je kunt winnen. Is je winkans hoger dan",
            "  dat aandeel, dan is callen op de lange duur winstgevend.",
            "TIGHT/LOOSE : een speler die weinig / veel handen speelt.",
            "PASSIEF/AGRESSIEF : een speler die liever callt / graag bet en raiset.",
            "RANGE : de lijst starthanden waarmee je in een situatie meedoet (openen, een raise callen, re-raisen).",
            "HEADS-UP : nog maar twee spelers in de hand of aan tafel; de button is dan ook small blind.",
            "PUSHEN / DUWEN : met een korte stack meteen all-in gaan in plaats van raisen ('push or fold').",
            "RE-SHOVE : met een korte stack all-in gaan over een raise van een ander heen.",
        ],
    ),
]

# (vraag, opties, juiste optie (1-gebaseerd), uitleg)
RULE_QUIZ: list[tuple[str, list[str], int, str]] = [
    (
        "Hoeveel eigen (dichte) kaarten krijgt elke speler in Texas Hold'em?",
        ["Twee", "Vier", "Vijf"],
        1,
        "Twee hole cards. Samen met de vijf open kaarten op tafel maak je je beste combinatie van vijf.",
    ),
    (
        "Welke kleur is het meest waard: schoppen, harten, ruiten of klaveren?",
        ["Schoppen", "Harten", "Geen enkele: alle kleuren zijn even veel waard"],
        3,
        "Kleuren hebben geen rangorde. Een schoppen aas en een harten aas zijn precies even sterk.",
    ),
    (
        "Wat betekent de 'o' in de starthand K5o?",
        [
            "De twee kaarten hebben een verschillende kleur (offsuit)",
            "Je hebt een paar",
            "De hand is 'open' voor een straight",
        ],
        1,
        "o = offsuit, s = suited (zelfde kleur). K5o is een heer en een vijf van verschillende kleur: "
        "heer 8 punten, gat van zeven kaarten -5, samen 3. Een zwakke hand.",
    ),
    (
        "Waarom moeten de small blind en de big blind vooraf inzetten?",
        [
            "Zodat er altijd iets in de pot ligt om voor te spelen",
            "Omdat zij de dealer betalen",
            "Als straf voor de spelers links van de button",
        ],
        1,
        "Zonder verplichte inzet zou iedereen kunnen wachten op perfecte kaarten. De blinds dwingen actie af "
        "en schuiven elke hand door, dus iedereen betaalt ze even vaak.",
    ),
    (
        "Niemand heeft vóór jou in deze ronde ingezet. Hoe blijf je meedoen zonder chips in te zetten?",
        ["Checken", "Callen", "Dat kan niet, je moet inzetten of passen"],
        1,
        "Checken is gratis de beurt doorgeven. Callen bestaat alleen als er een inzet ligt; passen zou zonde zijn.",
    ),
    (
        "Blinds 50/100. Speler A raiset naar 300. Wat is de minimale re-raise voor speler B?",
        ["Naar 400", "Naar 500", "Naar 600"],
        2,
        "De raise van A was 200 (van 100 naar 300); B moet minstens evenveel erbovenop: 300 + 200 = 500.",
    ),
    (
        "Wie handelt preflop als eerste aan een volle tafel?",
        ["De small blind", "De big blind", "De speler links van de big blind"],
        3,
        "Preflop begint de actie 'under the gun', links van de big blind. De blinds handelen als laatste.",
    ),
    (
        "Wie handelt na de flop als eerste?",
        ["De eerste actieve speler links van de button", "De button", "Wie preflop het laatst raisete"],
        1,
        "Postflop begint het altijd links van de button; de button handelt als laatste (positievoordeel).",
    ),
    (
        "Speler A heeft 500 chips en gaat all-in. B en C hebben 2000 en callen. Wie kan de zijpot winnen?",
        ["Alleen A", "Alleen B en C", "Iedereen"],
        2,
        "A heeft maar 500 ingezet en kan dus alleen de hoofdpot (3 x 500) winnen; B en C spelen om de rest.",
    ),
    (
        "Twee spelers hebben aan het einde exact dezelfde beste 5 kaarten. Wat gebeurt er?",
        ["De hoogste kleur wint", "De pot wordt gedeeld", "Wie het laatst raisete wint"],
        2,
        "Kleuren tellen niet mee in Hold'em; bij exact gelijke handen wordt de pot gedeeld.",
    ),
    (
        "Je hebt nog 8 big blinds in een toernooi en krijgt een speelbare hand. Wat is de vuistregel?",
        ["Push or fold: all-in of passen", "Altijd de minimale raise", "Altijd callen en de flop bekijken"],
        1,
        f"Met minder dan ongeveer {PUSH_FOLD_LIMIT:.0f} big blinds heb je te weinig chips om te raisen en daarna "
        "nog te folden. Je gaat all-in met een goede hand of je past.",
    ),
]
