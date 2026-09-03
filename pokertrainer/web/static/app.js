/* Poker Trainer - browserversie. Vanilla JavaScript, geen afhankelijkheden.
 *
 * De server stuurt spelgebeurtenissen via Server-Sent Events; elke gebeurtenis
 * bevat een momentopname van de tafel ("state"). Deze code tekent die
 * momentopname en voegt er alleen wat animatie en interactie aan toe.
 */
(() => {
  "use strict";

  // ---------- hulpjes ----------
  const $ = (selector, root = document) => root.querySelector(selector);

  function h(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "hidden") node.hidden = Boolean(value);
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat(Infinity)) {
      if (child == null || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  async function api(path, body, method) {
    const response = await fetch(path, {
      method: method || (body !== undefined ? "POST" : "GET"),
      headers: body !== undefined ? { "Content-Type": "application/json" } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
  }

  const fmt = (n) => Number(n).toLocaleString("nl-NL");

  function cardEl(text, cls = "") {
    if (!text) return h("div", { class: `card back ${cls}` });
    const suit = text.slice(-1);
    let rank = text.slice(0, -1);
    if (rank === "T") rank = "10";
    const red = suit === "♥" || suit === "♦";
    return h(
      "div",
      { class: `card ${red ? "red" : ""} ${cls}`, "data-card": text },
      h("span", { class: "corner" }, rank, h("br"), suit),
      h("span", { class: "pip" }, suit),
      h("span", { class: "corner flip" }, rank, h("br"), suit),
    );
  }

  const cardsEl = (cards, cls, wrapCls = "") =>
    h("div", { class: `cards ${wrapCls}` }, cards.map((c) => cardEl(c, cls)));

  // ---------- toestand ----------
  const app = { name: "Jij", model: null, content: null, session: null, stream: null, table: null, toastTimer: null };

  function showScreen(id) {
    document.querySelectorAll(".screen").forEach((s) => (s.hidden = s.id !== id));
    const onTable = id === "screen-table";
    $("#table-info").hidden = !onTable;
    $("#speed-control").hidden = !onTable;
    $("#btn-voice").hidden = !onTable;
    $("#btn-home").hidden = id === "screen-home";
    window.scrollTo(0, 0);
  }

  function toast(text, ms = 3200) {
    const node = $("#toast");
    node.textContent = text;
    node.hidden = false;
    clearTimeout(app.toastTimer);
    app.toastTimer = setTimeout(() => (node.hidden = true), ms);
  }

  function overlay(content) {
    const card = $("#overlay-card");
    card.innerHTML = "";
    card.append(content);
    $("#overlay").hidden = false;
  }
  const hideOverlay = () => ($("#overlay").hidden = true);

  async function goHome() {
    await leaveTable();
    showScreen("screen-home");
  }

  // ---------- startscherm ----------
  function renderHome() {
    const content = app.content;
    const root = $("#screen-home");
    root.innerHTML = "";
    root.append(
      h(
        "section",
        { class: "hero" },
        h("div", { class: "hero-suits" }, h("span", { class: "s-black" }, "♠"), h("span", { class: "s-red" }, "♥"), h("span", { class: "s-red" }, "♦"), h("span", { class: "s-black" }, "♣")),
        h("h1", {}, "Poker Trainer"),
        h("p", { class: "tagline" }, "Leer No-Limit Texas Hold'em zoals het op kampioenschappen wordt gespeeld."),
        h(
          "label",
          { class: "name-field" },
          "Hoe heet je?",
          h("input", {
            id: "player-name",
            value: app.name,
            maxlength: 16,
            oninput: (e) => (app.name = e.target.value.trim() || "Jij"),
          }),
        ),
        renderMethodChoice(),
      ),
      h(
        "section",
        { class: "lesson-grid" },
        content.lessons.map((lesson, index) =>
          h(
            "article",
            { class: "lesson-card", onclick: () => startLesson(lesson) },
            h("div", { class: "lesson-num" }, `Les ${index + 1}`),
            h("div", { class: "lesson-icon" }, lesson.icon),
            h("h2", {}, lesson.title),
            h("p", {}, lesson.description),
            h("button", { class: "btn gold small", type: "button" }, "Start"),
          ),
        ),
      ),
      h(
        "section",
        { class: "bots" },
        h("h3", {}, "Je tegenstanders"),
        h(
          "div",
          { class: "bot-list" },
          content.bots.map((bot) =>
            h(
              "div",
              { class: "bot" },
              h("div", { class: "avatar" }, bot.name[0]),
              h("div", {}, h("strong", {}, bot.name), h("div", { class: "muted" }, bot.description)),
            ),
          ),
        ),
      ),
    );
  }

  /** Keuze van de coachmethode (starthandmodel) voor de tafels. */
  function renderMethodChoice() {
    const coach = app.content.coach;
    if (!app.model) app.model = coach.default;
    const box = h("div", { class: "method-field" }, h("span", { class: "label" }, "Coachmethode voor starthanden"));
    const options = h("div", { class: "options" });
    for (const model of coach.models) {
      options.append(
        h(
          "button",
          {
            class: `option ${model.key === app.model ? "chosen" : ""}`,
            type: "button",
            onclick: () => {
              app.model = model.key;
              options.querySelectorAll(".option").forEach((el) => el.classList.toggle("chosen", el.dataset.key === model.key));
            },
            "data-key": model.key,
          },
          h("strong", {}, model.name),
          h("small", {}, model.description),
        ),
      );
    }
    box.append(options);
    return box;
  }

  function startLesson(lesson) {
    if (lesson.kind === "ranking") startRanking();
    else if (lesson.kind === "rules") startRules();
    else startTable(lesson.key);
  }

  // ---------- gedeelde quizonderdelen ----------
  function lessonShell(title, subtitle) {
    const root = $("#screen-lesson");
    root.innerHTML = "";
    const wrap = h("div", { class: "lesson" }, h("header", { class: "lesson-head" }, h("h1", {}, title), subtitle && h("p", { class: "muted" }, subtitle)));
    root.append(wrap);
    showScreen("screen-lesson");
    return wrap;
  }

  function progressEl(current, total, history) {
    return h(
      "div",
      { class: "progress" },
      Array.from({ length: total }, (_, i) =>
        h("span", { class: `dot ${i < history.length ? (history[i] ? "ok" : "nok") : i === current ? "now" : ""}` }),
      ),
    );
  }

  /** Eén meerkeuzevraag met feedback; roept onDone(ok) aan bij "Volgende". */
  function renderQuestion(box, spec) {
    box.innerHTML = "";
    const card = h("div", { class: "quiz-card" });
    card.append(
      h(
        "div",
        { class: "quiz-head" },
        h("div", {}, h("h2", {}, spec.title), spec.subtitle && h("p", { class: "muted" }, spec.subtitle)),
        progressEl(spec.index, spec.total, spec.history),
      ),
      spec.body,
    );
    const feedback = h("div", { class: "feedback", hidden: true });
    const options = h("div", { class: `options ${spec.options.length > 4 ? "cols-2" : ""}` });
    let answered = false;
    for (const option of spec.options) {
      const button = h(
        "button",
        {
          class: "option",
          type: "button",
          "data-key": option.key,
          onclick: () => {
            if (answered) return;
            answered = true;
            const ok = String(option.key) === String(spec.correctKey);
            options.querySelectorAll(".option").forEach((el) => {
              el.disabled = true;
              if (el.dataset.key === String(spec.correctKey)) el.classList.add("correct");
            });
            if (!ok) button.classList.add("wrong");
            feedback.hidden = false;
            feedback.className = `feedback ${ok ? "ok" : "nok"}`;
            feedback.append(h("strong", {}, ok ? "✔ Juist! " : "✘ Nee. "), spec.explain(ok));
            if (spec.onAnswered) spec.onAnswered(ok);
            feedback.append(h("div", { class: "actions" }, h("button", { class: "btn gold", type: "button", onclick: () => spec.onDone(ok) }, spec.lastLabel || "Volgende")));
            feedback.querySelector(".btn").focus();
          },
        },
        option.label,
      );
      options.append(button);
    }
    card.append(options, feedback);
    box.append(card);
  }

  function renderResults(box, title, parts, onRetry) {
    const total = parts.reduce((s, p) => s + p.total, 0);
    const score = parts.reduce((s, p) => s + p.score, 0);
    const ratio = score / total;
    const verdict = ratio === 1 ? "Foutloos. Klaar voor de tafel!" : ratio >= 0.7 ? "Goed bezig. Nog één keer en je hebt het helemaal onder de knie." : "Neem de uitleg nog eens door en probeer het opnieuw: herhaling is de sleutel.";
    box.innerHTML = "";
    box.append(
      h(
        "div",
        { class: "quiz-card result" },
        h("h2", {}, title),
        parts.map((p) => h("div", { class: "score-row" }, h("span", {}, p.label), h("strong", {}, `${p.score} / ${p.total}`))),
        h("p", { class: "muted" }, verdict),
        h("div", { class: "actions" }, h("button", { class: "btn gold", type: "button", onclick: onRetry }, "Nog een keer"), h("button", { class: "btn ghost", type: "button", onclick: goHome }, "Terug naar het menu")),
      ),
    );
  }

  // ---------- les 1: handrangschikking ----------
  function startRanking() {
    const wrap = lessonShell("Handrangschikking", "Je maakt de beste hand van vijf kaarten uit je twee eigen kaarten en de vijf op tafel. Van sterk naar zwak:");
    const categories = app.content.ranking.categories;
    wrap.append(
      h(
        "div",
        { class: "ranking-table" },
        categories.map((c) =>
          h("div", { class: "ranking-row" }, h("div", { class: "num" }, c.rank), h("div", {}, h("strong", {}, c.name), h("div", { class: "muted" }, c.explanation)), cardsEl(c.example, "sm")),
        ),
      ),
      h("p", { class: "note" }, "Bij gelijke categorie beslist de hoogste kaart (kicker); bij volledig gelijke handen wordt de pot gedeeld. Kleuren (♠ ♥ ♦ ♣) zijn nooit hoger dan elkaar."),
      h("div", { class: "actions" }, h("button", { class: "btn gold", type: "button", onclick: () => runRankingQuiz(wrap) }, "Start de quiz"), h("button", { class: "btn ghost", type: "button", onclick: goHome }, "Terug")),
    );
  }

  async function runRankingQuiz(wrap) {
    let quiz;
    try {
      quiz = await api("/api/quiz/ranking");
    } catch (error) {
      toast(error.message);
      return;
    }
    const categories = app.content.ranking.categories;
    const box = h("div");
    wrap.innerHTML = "";
    wrap.append(box);
    const history1 = [];
    const history2 = [];

    const askRanking = (i) => {
      if (i >= quiz.questions.length) return askShowdown(0);
      const q = quiz.questions[i];
      renderQuestion(box, {
        title: "Oefening 1 · Welke hand is dit?",
        subtitle: "Zeven kaarten. Kies de categorie van de beste combinatie van vijf.",
        index: i,
        total: quiz.questions.length,
        history: history1,
        body: cardsEl(q.cards, "lg", "quiz-cards"),
        options: categories.map((c) => ({ key: c.key, label: `${c.rank}. ${c.name}` })),
        correctKey: q.category,
        explain: (ok) => (ok ? `${q.answer}.` : `Het is: ${q.answer}.`),
        onAnswered: () => {
          box.querySelectorAll(".quiz-cards .card").forEach((el) => {
            if (!q.best_five.includes(el.dataset.card)) el.classList.add("dim");
          });
        },
        onDone: (ok) => {
          history1.push(ok);
          askRanking(i + 1);
        },
      });
    };

    const askShowdown = (i) => {
      if (i >= quiz.showdowns.length) {
        return renderResults(
          box,
          "Resultaat handrangschikking",
          [
            { label: "Welke hand is dit?", score: history1.filter(Boolean).length, total: history1.length },
            { label: "Wie wint de showdown?", score: history2.filter(Boolean).length, total: history2.length },
          ],
          () => runRankingQuiz(wrap),
        );
      }
      const q = quiz.showdowns[i];
      const row = (label, cards, cls) => h("div", { class: "row" }, h("span", { class: "label" }, label), cardsEl(cards, cls));
      renderQuestion(box, {
        title: "Oefening 2 · Wie wint de showdown?",
        subtitle: "Beide spelers gebruiken de beste vijf van hun zeven kaarten.",
        index: i,
        total: quiz.showdowns.length,
        history: history2,
        body: h("div", { class: "showdown-q" }, row("Board", q.board, ""), row("Speler A", q.hand_a, ""), row("Speler B", q.hand_b, "")),
        options: [
          { key: 1, label: "Speler A wint" },
          { key: 2, label: "Speler B wint" },
          { key: 3, label: "Gedeelde pot" },
        ],
        correctKey: q.correct,
        explain: () => `A: ${q.describe_a}  ·  B: ${q.describe_b}.`,
        lastLabel: i === quiz.showdowns.length - 1 ? "Naar het resultaat" : "Volgende",
        onDone: (ok) => {
          history2.push(ok);
          askShowdown(i + 1);
        },
      });
    };
    askRanking(0);
  }

  // ---------- les 2: regels ----------
  /** Zet de consoleregels om in nette HTML: opsommingen, definities en vervolgregels. */
  function formatLines(lines) {
    const merged = [];
    for (const raw of lines) {
      if (/^\s/.test(raw) && merged.length) merged[merged.length - 1] += " " + raw.trim();
      else merged.push(...raw.trim().split(/\s{2,}(?=\d+\.\s)/)); // "5. TURN …  6. RIVER …" → twee punten
    }
    const out = h("div");
    let list = null;
    let paragraph = null;
    const startsBlock = (line) => /^(Voorbeeld|Tip|Doel)\b/.test(line);
    for (const line of merged) {
      let m;
      if ((m = line.match(/^(\d+)\.\s+(.*)$/))) {
        paragraph = null;
        if (!list || list.tagName !== "OL") { list = h("ol"); out.append(list); }
        list.append(h("li", {}, splitExample(m[2])));
      } else if ((m = line.match(/^•\s*(.*)$/))) {
        paragraph = null;
        if (!list || list.tagName !== "UL") { list = h("ul"); out.append(list); }
        list.append(h("li", {}, splitExample(m[1])));
      } else if ((m = line.match(/^([A-Z][A-Z\-\/ ]{1,16}?)\s*:\s+(.*)$/))) {
        list = null;
        paragraph = null;
        out.append(h("p", { class: "definition" }, h("span", { class: "term" }, m[1]), splitExample(m[2])));
      } else if (paragraph && !startsBlock(line)) {
        paragraph.append(" ", ...splitExample(line)); // zelfde alinea: de consoleregels lopen door
      } else {
        list = null;
        paragraph = h("p", {}, splitExample(line));
        out.append(paragraph);
      }
    }
    return out;
  }
  function splitExample(text) {
    const idx = text.indexOf("Voorbeeld:");
    if (idx < 0) return [text];
    return [text.slice(0, idx), h("span", { class: "example" }, "Voorbeeld:"), text.slice(idx + "Voorbeeld:".length)];
  }

  function startRules() {
    const pages = app.content.rules.pages;
    const wrap = lessonShell("Regels van toernooipoker", "Nog nooit een kaartspel gespeeld? Geen probleem. We beginnen bij het kaartspel zelf en eindigen bij de regels van een kampioenschap. No-limit betekent: je mag op elk moment alles inzetten wat je voor je hebt.");
    const box = h("div");
    wrap.append(box);
    let i = 0;
    const show = () => {
      box.innerHTML = "";
      const page = pages[i];
      box.append(
        h(
          "div",
          { class: "slide" },
          h("div", { class: "slide-num" }, `Deel ${i + 1} van ${pages.length}`),
          h("h2", {}, page.heading),
          formatLines(page.lines),
          /starthanden/i.test(page.heading) && renderTryHand(),
          h(
            "div",
            { class: "actions" },
            i > 0 && h("button", { class: "btn ghost", type: "button", onclick: () => { i--; show(); } }, "Vorige"),
            i < pages.length - 1
              ? h("button", { class: "btn gold", type: "button", onclick: () => { i++; show(); } }, "Volgende")
              : h("button", { class: "btn gold", type: "button", onclick: () => runRulesQuiz(wrap) }, "Naar de quiz"),
            h("button", { class: "btn ghost", type: "button", onclick: goHome }, "Menu"),
          ),
        ),
      );
    };
    show();
  }

  /** Probeer zelf: een starthand en positie invoeren en beide methodes vergelijken. */
  function renderTryHand() {
    const input = h("input", { value: "K5o", maxlength: 3, placeholder: "K5o" });
    const select = h("select", {}, app.content.positions.map((p) => h("option", { value: p.key, selected: p.key === "button" }, p.name)));
    const situation = h("select", {}, app.content.situations.map((s) => h("option", { value: s.key }, s.name)));
    const stack = h("input", { type: "number", value: 8, min: 1, max: 30, step: 1, title: "big blinds", class: "num" });
    const behind = h("input", { type: "number", value: 1, min: 0, max: 9, step: 1, title: "spelers achter je", class: "num" });
    const behindPart = h("span", { class: "row-part" }, h("span", {}, ", tegenstanders die kunnen callen"), behind);
    const shortRow = h("div", { class: "row", hidden: true }, h("span", {}, "Stack (of de all-in als die kleiner is)"), stack, h("span", {}, "big blinds"), behindPart);
    situation.addEventListener("change", () => {
      shortRow.hidden = !/^(push|call)$/.test(situation.value);
      behindPart.hidden = situation.value !== "push";
    });
    const results = h("div", { class: "verdicts" });
    const check = async () => {
      results.innerHTML = "";
      try {
        const query = new URLSearchParams({ hand: input.value, positie: select.value, situatie: situation.value, stack: stack.value, achter: behind.value });
        const data = await api(`/api/starthand?${query}`);
        for (const model of data.models) {
          results.append(
            h(
              "div",
              { class: "verdict-card" },
              h("h4", {}, model.name),
              h("div", { class: `verdict ${model.fold ? "fold" : ""}` }, `${data.hand}: ${model.advice}`),
              h("ul", {}, model.lines.map((line) => h("li", {}, line))),
            ),
          );
        }
      } catch (error) {
        results.append(h("p", { class: "muted" }, error.message));
      }
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") check(); });
    return h(
      "div",
      { class: "try-box" },
      h("h3", {}, "Probeer zelf: wat zegt de coach, en waarom?"),
      h("div", { class: "row" }, h("span", {}, "Starthand"), input, h("span", {}, "op positie"), select, h("span", {}, "als"), situation, h("button", { class: "btn gold small", type: "button", onclick: check }, "Beoordeel")),
      shortRow,
      results,
    );
  }

  function runRulesQuiz(wrap) {
    const quiz = app.content.rules.quiz;
    const box = h("div");
    wrap.innerHTML = "";
    wrap.append(box);
    const history = [];
    const ask = (i) => {
      if (i >= quiz.length) {
        return renderResults(box, "Resultaat regelquiz", [{ label: "Regels van toernooipoker", score: history.filter(Boolean).length, total: history.length }], () => runRulesQuiz(wrap));
      }
      const q = quiz[i];
      renderQuestion(box, {
        title: "Korte quiz over de regels",
        subtitle: null,
        index: i,
        total: quiz.length,
        history,
        body: h("p", { class: "question" }, q.question),
        options: q.options.map((label, idx) => ({ key: idx + 1, label })),
        correctKey: q.correct,
        explain: () => q.explanation,
        lastLabel: i === quiz.length - 1 ? "Naar het resultaat" : "Volgende",
        onDone: (ok) => {
          history.push(ok);
          ask(i + 1);
        },
      });
    };
    ask(0);
  }

  // ---------- de tafel ----------
  const currentSpeed = () => Number($("#speed").value) || 1;

  async function startTable(lessonKey) {
    await leaveTable();
    let session;
    try {
      session = await api("/api/sessions", { name: app.name, model: app.model });
    } catch (error) {
      toast(`Kan geen sessie starten: ${error.message}`);
      return;
    }
    app.session = session.id;
    app.table = {
      lesson: lessonKey,
      humanName: session.name,
      seats: new Map(),
      boardKey: "",
      decision: null,
      autoAdvice: false,
      eliminatedPlace: null,
      tournamentResult: null,
    };
    resetTableUI();
    showScreen("screen-table");
    openStream();
    try {
      await api(`/api/sessions/${app.session}/table`, { lesson: lessonKey, speed: currentSpeed() });
    } catch (error) {
      toast(error.message);
    }
  }

  function openStream() {
    const stream = new EventSource(`/api/sessions/${app.session}/stream`);
    stream.onmessage = (e) => handleEvent(JSON.parse(e.data));
    stream.onerror = () => {}; // EventSource verbindt zelf opnieuw
    app.stream = stream;
  }

  async function leaveTable() {
    if (app.stream) {
      app.stream.close();
      app.stream = null;
    }
    if (app.session) {
      const id = app.session;
      app.session = null;
      api(`/api/sessions/${id}/quit`, {}).catch(() => {});
    }
    app.table = null;
    hideOverlay();
  }

  function resetTableUI() {
    $("#seats").innerHTML = "";
    $("#board").innerHTML = "";
    $("#pot").hidden = true;
    $("#log-body").innerHTML = "";
    $("#coach-body").innerHTML = "";
    $("#info-title").textContent = "";
    $("#info-model").textContent = "";
    $("#info-hand").textContent = "";
    $("#info-level").textContent = "";
    hideActionBar();
    $("#btn-advice").disabled = true;
  }

  function buildSeats(state) {
    const seatsEl = $("#seats");
    seatsEl.innerHTML = "";
    app.table.seats.clear();
    const count = state.seats.length;
    const humanIndex = Math.max(0, state.seats.findIndex((s) => s.is_human));
    state.seats.forEach((s, index) => {
      const angle = Math.PI / 2 + ((index - humanIndex) * 2 * Math.PI) / count; // mens onderaan
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const x = 50 + 41 * cos;
      const y = 50 + 37 * sin;
      const bx = 50 + 26 * cos;
      const by = 50 + 20 * sin;
      const seat = h(
        "div",
        { class: `seat ${s.is_human ? "me" : ""}`, style: `left:${x}%; top:${y}%`, title: s.style || "" },
        h("div", { class: "cards" }),
        h("div", { class: "plate" }, h("div", { class: "name" }, s.name), h("div", { class: "chips" }), h("div", { class: "hand-label" }), h("div", { class: "badge", hidden: true })),
      );
      const bet = h("div", { class: "bet", hidden: true, style: `left:${bx}%; top:${by}%` }, h("span", { class: "chip" }), h("span", { class: "amount" }));
      const dealerX = bx + (Math.abs(cos) < 0.2 ? 9 : 6 * Math.sign(cos));
      const dealerY = by + (Math.abs(cos) < 0.2 ? 0 : -7 * Math.sign(sin || 1));
      const dealer = h("div", { class: "dealer", hidden: true, style: `left:${dealerX}%; top:${dealerY}%` }, "D");
      seatsEl.append(seat, bet, dealer);
      app.table.seats.set(s.name, { seat, bet, dealer, cardsKey: "" });
    });
  }

  function renderState(state) {
    const t = app.table;
    if (!t) return;
    $("#info-hand").textContent = state.hand_number ? `Hand ${state.hand_number}` : "";
    $("#info-level").textContent = state.level ? `Blinds ${state.level.text}` : "";

    // board: alleen nieuwe kaarten toevoegen, zodat de deel-animatie klopt
    const boardEl = $("#board");
    const key = state.board.join(" ");
    if (key !== t.boardKey) {
      if (!key.startsWith(t.boardKey) || !t.boardKey) boardEl.innerHTML = "";
      boardEl.querySelectorAll(".slot").forEach((el) => el.remove());
      const shown = boardEl.querySelectorAll(".card").length;
      state.board.slice(shown).forEach((c) => boardEl.append(cardEl(c, "deal")));
      t.boardKey = key;
    }
    boardEl.querySelectorAll(".slot").forEach((el) => el.remove());
    for (let i = state.board.length; i < 5; i++) boardEl.append(h("div", { class: "card slot" }));

    const potEl = $("#pot");
    potEl.hidden = !state.pot;
    potEl.textContent = state.pot ? `Pot ${fmt(state.pot)}` : "";

    for (const s of state.seats) {
      const ref = t.seats.get(s.name);
      if (!ref) continue;
      const folded = s.folded && s.in_hand;
      ref.seat.classList.toggle("folded", folded);
      ref.seat.classList.toggle("out", s.out);
      ref.seat.querySelector(".chips").textContent = fmt(s.chips);
      const badge = ref.seat.querySelector(".badge");
      const badgeText = s.out ? "UIT" : s.all_in ? "ALL-IN" : folded ? "FOLD" : "";
      badge.hidden = !badgeText;
      badge.textContent = badgeText;
      badge.className = `badge ${badgeText.toLowerCase().replace("-", "")}`;

      let cards = [];
      if (s.in_hand && s.cards && (!folded || s.is_human)) cards = s.cards;
      else if (s.in_hand && !folded) cards = [null, null];
      const cardsKey = cards.map((c) => c || "?").join(" ");
      if (cardsKey !== ref.cardsKey) {
        const box = ref.seat.querySelector(".cards");
        box.innerHTML = "";
        cards.forEach((c, i) => {
          const el = cardEl(c, s.is_human ? "deal" : "deal sm");
          el.style.animationDelay = `${i * 110}ms`;
          box.append(el);
        });
        ref.cardsKey = cardsKey;
      }
      ref.seat.querySelector(".hand-label").textContent = s.hand ? s.hand.text : "";
      ref.bet.hidden = !s.bet;
      ref.bet.querySelector(".amount").textContent = fmt(s.bet);
      ref.dealer.hidden = !s.is_button;
    }
  }

  function setActive(name) {
    for (const [seatName, ref] of app.table.seats) ref.seat.classList.toggle("active", seatName === name);
  }
  const clearActive = () => setActive(null);

  function bubble(name, action) {
    const ref = app.table.seats.get(name);
    if (!ref) return;
    ref.seat.querySelector(".bubble")?.remove();
    ref.seat.append(h("div", { class: `bubble ${action.type.replace("-", "")}` }, action.text));
  }
  function clearBubbles() {
    for (const ref of app.table.seats.values()) {
      ref.seat.querySelector(".bubble")?.remove();
      ref.seat.classList.remove("winner");
    }
  }

  function celebrate(name, amount) {
    const ref = app.table.seats.get(name);
    if (!ref) return;
    ref.seat.classList.add("winner");
    const float = h("div", { class: "win-float" }, `+${fmt(amount)}`);
    ref.seat.append(float);
    setTimeout(() => float.remove(), 1700);
    const pot = $("#pot");
    pot.classList.remove("flash");
    void pot.offsetWidth;
    pot.classList.add("flash");
  }

  function log(text, cls = "") {
    const body = $("#log-body");
    body.append(h("div", { class: `line ${cls}` }, text));
    while (body.children.length > 400) body.firstChild.remove();
    body.scrollTop = body.scrollHeight;
  }

  function coachIntro(ev) {
    const body = $("#coach-body");
    body.innerHTML = "";
    body.append(
      h(
        "p",
        { class: "coach-line" },
        ev.auto_advice
          ? "Welkom aan de oefentafel. Bij elke beslissing vertel ik wat ik zou doen en waarom. Je hoeft mijn advies niet te volgen: proberen en fouten maken is de bedoeling. Wie zonder chips valt, koopt automatisch opnieuw in."
          : "Welkom bij het toernooi. Ik zwijg zolang je me niets vraagt; druk op “Vraag advies” (of ?) als je hulp wilt. Wie als laatste overblijft, wint.",
      ),
    );
  }
  function coachLine(text) {
    const body = $("#coach-body");
    body.append(h("p", { class: "coach-line" }, "🎓 ", text));
    body.scrollTop = body.scrollHeight;
  }
  function coachAdvice(advice) {
    const body = $("#coach-body");
    const lines = advice.lines.filter((line) => !line.startsWith("ADVIES"));
    const block = h("div", { class: "advice" }, h("div", { class: "verdict" }, `Advies: ${advice.action.imperative}`), h("ul", {}, lines.map((line) => h("li", {}, line))));
    body.append(block);
    body.scrollTop = block.offsetTop - 10; // het advies bovenaan in beeld, ook als het lang is
    applyAdvisedAmount(advice.action);
  }

  /** Zet slider, invoerveld en knop op het bedrag dat de coach adviseert, met een preset 'Coach'. */
  function applyAdvisedAmount(action) {
    const t = app.table;
    if (!t || !t.raiseSync || !action.amount || !/^(bet|raise)$/.test(action.type)) return;
    const presets = $("#raise-presets");
    presets.querySelector(".preset.coach")?.remove();
    presets.prepend(h("button", { class: "preset coach", type: "button", onclick: () => t.raiseSync(action.amount) }, `Coach ${fmt(action.amount)}`));
    t.raiseSync(action.amount);
  }

  // --- de croupier spreekt: tekstballon en (optioneel) spraaksynthese ---
  const RANK_WORDS = { A: "aas", K: "heer", Q: "vrouw", J: "boer", T: "tien" };
  const SUIT_WORDS = { "♠": "schoppen", "♥": "harten", "♦": "ruiten", "♣": "klaveren" };
  const cardWords = (card) => `${SUIT_WORDS[card.slice(-1)]} ${RANK_WORDS[card.slice(0, -1)] || card.slice(0, -1)}`;
  const cardsWords = (cards) => cards.map(cardWords).join(", ");

  const voice = {
    enabled: false,
    supported: "speechSynthesis" in window,
    timer: null,
    load() {
      try { this.enabled = localStorage.getItem("croupier-voice") === "aan"; } catch (_) { this.enabled = false; }
      this.render();
    },
    toggle() {
      this.enabled = !this.enabled;
      try { localStorage.setItem("croupier-voice", this.enabled ? "aan" : "uit"); } catch (_) { /* geen opslag */ }
      this.render();
      if (this.enabled) say("Goedenavond. Ik deel de kaarten voor u.");
      else if (this.supported) speechSynthesis.cancel();
    },
    render() {
      const button = $("#btn-voice");
      button.textContent = this.enabled ? "🔊 Stem aan" : "🔇 Stem";
      button.disabled = !this.supported;
      if (!this.supported) button.title = "Deze browser heeft geen spraaksynthese.";
    },
    pick() {
      const voices = speechSynthesis.getVoices();
      return voices.find((v) => /^nl[-_]BE/i.test(v.lang)) || voices.find((v) => /^nl/i.test(v.lang)) || null;
    },
    speak(text) {
      if (!this.enabled || !this.supported) return;
      if (speechSynthesis.speaking && speechSynthesis.pending) speechSynthesis.cancel(); // achterstand wegwerken
      const utterance = new SpeechSynthesisUtterance(text);
      const chosen = this.pick();
      if (chosen) utterance.voice = chosen;
      utterance.lang = chosen ? chosen.lang : "nl-NL";
      utterance.rate = 1.05;
      utterance.pitch = 1.1;
      speechSynthesis.speak(utterance);
    },
  };

  /** Toont een tekstballon bij de croupier; `spoken` is de variant voor de stem (kaarten voluit).
   *  Elke boodschap blijft minstens even staan; wat sneller volgt, wacht netjes zijn beurt af. */
  let speechReadyAt = 0;
  function say(text, spoken = text, holdMs = 2600) {
    const now = performance.now();
    const wait = Math.max(0, speechReadyAt - now);
    speechReadyAt = now + wait + Math.max(900, dealDelay(1700));
    setTimeout(() => showSpeech(text, spoken, holdMs), wait);
  }
  function showSpeech(text, spoken, holdMs) {
    const bubble = $("#speech");
    if (!app.table) return;
    bubble.textContent = text;
    bubble.hidden = false;
    bubble.classList.remove("fade");
    clearTimeout(voice.timer);
    voice.timer = setTimeout(() => bubble.classList.add("fade"), Math.max(1200, dealDelay(holdMs)));
    voice.speak(spoken);
  }

  const STREET_NAMES = { flop: "De flop", turn: "De turn", river: "De river" };

  // --- deel-animaties: de croupier gooit kaarten naar stoelen, board en burn-stapel ---
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const dealDelay = (ms) => ms / currentSpeed();

  function swingArm() {
    const arm = $("#croupier-arm");
    arm.classList.remove("swing");
    void arm.getBoundingClientRect();
    arm.classList.add("swing");
  }

  /** Laat een kaartrug (of fiche) van `fromEl` naar `toEl` vliegen; lost op bij aankomst. */
  function fly(fromEl, toEl, { delay = 0, duration = 420, spin = 1, chip = false } = {}) {
    return new Promise((resolve) => {
      const layer = $("#fly-layer");
      if (!fromEl || !toEl || !layer || reducedMotion) return resolve();
      const base = layer.getBoundingClientRect();
      const a = fromEl.getBoundingClientRect();
      const b = toEl.getBoundingClientRect();
      if (!a.width || !b.width) return resolve();
      const node = chip ? h("span", { class: "chip" }) : h("div", { class: "card back sm" });
      const w = chip ? 22 : 40;
      const hgt = chip ? 22 : 56;
      node.style.left = `${a.left + a.width / 2 - base.left - w / 2}px`;
      node.style.top = `${a.top + a.height / 2 - base.top - hgt / 2}px`;
      layer.append(node);
      const dx = b.left + b.width / 2 - (a.left + a.width / 2);
      const dy = b.top + b.height / 2 - (a.top + a.height / 2);
      const animation = node.animate(
        [
          { transform: "translate(0, 0) rotate(0deg) scale(.75)", opacity: 0.85 },
          { transform: `translate(${dx}px, ${dy}px) rotate(${spin * 300}deg) scale(1)`, opacity: 1 },
        ],
        { duration: dealDelay(duration), delay: dealDelay(delay), easing: "cubic-bezier(.2, .75, .3, 1)", fill: "forwards" },
      );
      if (!chip) setTimeout(swingArm, dealDelay(delay));
      // In een achtergrondtabblad levert de browser 'finish'-events soms pas veel later af;
      // de tijdslimiet garandeert dat de kaart hoe dan ook aankomt.
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        node.remove();
        resolve();
      };
      animation.finished.then(finish, finish);
      setTimeout(finish, dealDelay(delay + duration) + 80);
    });
  }

  /** Verbergt een kaart tot de vliegende rug is aangekomen en laat hem dan omdraaien. */
  function dealInto(cardEl, delay) {
    if (!cardEl) return Promise.resolve();
    cardEl.classList.add("pending");
    cardEl.classList.remove("deal");
    return fly($("#croupier-hand"), cardEl, { delay }).then(() => {
      if (!cardEl.isConnected) return;
      cardEl.classList.remove("pending");
      cardEl.classList.add("arrive");
    });
  }

  function dealHoleCards(order) {
    const t = app.table;
    let index = 0;
    for (let round = 0; round < 2; round++) {
      for (const name of order) {
        const ref = t.seats.get(name);
        const cardEl = ref && ref.seat.querySelectorAll(".cards .card")[round];
        if (cardEl) dealInto(cardEl, index * 120);
        index++;
      }
    }
  }

  function dealBoard(count) {
    const cards = [...$("#board").querySelectorAll(".card:not(.slot)")].slice(-count);
    cards.forEach((cardEl, i) => dealInto(cardEl, i * 170));
  }

  function burnCard() {
    const pile = $("#burn-pile");
    fly($("#croupier-hand"), pile, { duration: 360, spin: 0.5 }).then(() => {
      const card = h("div", { class: "card back" });
      card.style.transform = `rotate(${(Math.random() - 0.5) * 24}deg) translate(${pile.children.length * 2}px, 0)`;
      pile.append(card);
    });
  }

  function chipsToWinner(name) {
    const ref = app.table.seats.get(name);
    if (!ref) return;
    for (let i = 0; i < 4; i++) fly($("#pot"), ref.seat.querySelector(".plate"), { delay: i * 70, duration: 520, chip: true });
  }

  // --- beslissing van de mens ---
  function showDecision(d) {
    const t = app.table;
    t.decision = d;
    setActive(t.humanName);
    $("#waiting").hidden = true;
    const bar = $("#action-bar");
    bar.hidden = false;
    bar.classList.remove("busy");
    $("#sit-street").textContent = d.street.toUpperCase();
    $("#sit-pot").textContent = fmt(d.pot);
    $("#sit-call").textContent = fmt(d.to_call);
    $("#sit-odds").textContent = d.to_call ? `${Math.round(d.pot_odds * 100)}%` : "–";
    $("#sit-pos").textContent = d.position;

    const legal = d.legal;
    const buttons = $("#action-buttons");
    buttons.innerHTML = "";
    if (legal.can_check) {
      buttons.append(h("button", { class: "btn call", type: "button", onclick: () => sendAction("check") }, "Check"));
    } else {
      buttons.append(h("button", { class: "btn fold", type: "button", onclick: () => sendAction("fold") }, "Fold"));
      buttons.append(h("button", { class: "btn call", type: "button", onclick: () => sendAction("call") }, `Call ${fmt(legal.call_amount)}`));
    }
    const canSize = legal.can_raise && legal.min_raise_to < legal.max_raise_to;
    $("#raise-box").hidden = !canSize;
    t.raiseSync = null;
    if (canSize) buttons.append(setupRaise(d));
    buttons.append(h("button", { class: "btn allin", type: "button", onclick: () => sendAction("all-in") }, `All-in ${fmt(legal.max_raise_to)}`));
    $("#btn-advice").disabled = false;
    if (d.advice) coachAdvice(d.advice);
  }

  function setupRaise(d) {
    const legal = d.legal;
    const verb = d.current_bet === 0 ? "Bet" : "Raise naar";
    const slider = $("#raise-slider");
    const input = $("#raise-input");
    const button = h("button", { class: "btn raise", type: "button" });
    slider.min = input.min = legal.min_raise_to;
    slider.max = input.max = legal.max_raise_to;
    const sync = (value) => {
      const v = Math.max(legal.min_raise_to, Math.min(legal.max_raise_to, Math.round(Number(value) || legal.min_raise_to)));
      slider.value = v;
      input.value = v;
      button.textContent = `${verb} ${fmt(v)}`;
    };
    slider.oninput = () => sync(slider.value);
    input.onchange = () => sync(input.value);
    button.onclick = () => sendAction("raise", Number(slider.value));
    app.table.raiseSync = sync;

    const unit = Math.max(1, Math.floor(d.big_blind / 2));
    const round = (v) => Math.round(v / unit) * unit;
    const potAfterCall = d.pot + d.to_call;
    const base = d.my_bet + d.to_call;
    const presets = $("#raise-presets");
    presets.innerHTML = "";
    [
      ["Min", legal.min_raise_to],
      ["½ pot", round(base + 0.5 * potAfterCall)],
      ["⅔ pot", round(base + 0.66 * potAfterCall)],
      ["Pot", round(base + potAfterCall)],
      ["Max", legal.max_raise_to],
    ].forEach(([label, value]) => presets.append(h("button", { class: "preset", type: "button", onclick: () => sync(value) }, label)));
    sync(legal.min_raise_to);
    return button;
  }

  async function sendAction(type, amount) {
    const t = app.table;
    if (!t || !t.decision) return;
    t.decision = null;
    $("#action-bar").classList.add("busy");
    try {
      await api(`/api/sessions/${app.session}/action`, { type, amount: amount || 0 });
    } catch (error) {
      toast(error.message);
    }
  }

  function hideActionBar() {
    $("#action-bar").hidden = true;
    $("#waiting").hidden = !app.table;
    if (app.table) app.table.decision = null;
  }

  async function askAdvice() {
    if (!app.session || !app.table || !app.table.decision) return;
    try {
      coachAdvice(await api(`/api/sessions/${app.session}/advice`, {}));
    } catch (error) {
      toast(error.message);
    }
  }

  function showSummary(ev) {
    const t = app.table;
    let title;
    if (ev.outcome === "quit") title = "Je hebt de tafel verlaten";
    else if (ev.outcome === "error") title = "Er ging iets mis aan tafel";
    else if (t.tournamentResult) title = ev.won ? "🏆 Je wint het toernooi!" : `🏆 ${t.tournamentResult.winner} wint het toernooi`;
    else if (t.eliminatedPlace) title = `Uitgeschakeld op plaats ${t.eliminatedPlace}`;
    else title = "Einde van de oefentafel";
    const stat = (k, v) => h("div", { class: "stat" }, h("div", { class: "v" }, fmt(v)), h("div", { class: "k" }, k));
    overlay(
      h(
        "div",
        {},
        h("h2", {}, title),
        h("p", { class: "muted" }, `Je eindigt met ${fmt(ev.chips)} chips.`),
        h("div", { class: "stats" }, stat("Handen", ev.hands), stat("Gewonnen", ev.hands_won), stat("Preflop gefold", ev.folded_preflop), stat("Showdowns", ev.showdowns)),
        t.tournamentResult && h("div", {}, h("strong", {}, "Eindstand"), h("ol", { class: "ranking-list" }, t.tournamentResult.ranking.map((name) => h("li", {}, name)))),
        h(
          "div",
          { class: "actions" },
          h("button", { class: "btn gold", type: "button", onclick: () => startTable(t.lesson) }, "Nog een keer"),
          h("button", { class: "btn ghost", type: "button", onclick: goHome }, "Terug naar het menu"),
        ),
      ),
    );
  }

  function handleEvent(ev) {
    const t = app.table;
    if (!t) return;
    switch (ev.type) {
      case "table_started":
        t.autoAdvice = ev.auto_advice;
        t.humanName = ev.human;
        $("#info-title").textContent = ev.title;
        $("#info-model").textContent = ev.model ? `Coach: ${ev.model.name.split(":")[0]}` : "";
        buildSeats(ev.state);
        renderState(ev.state);
        coachIntro(ev);
        log(ev.title, "hand");
        $("#waiting").hidden = false;
        say("Welkom aan tafel. Shuffle up and deal!");
        break;
      case "hand_started":
        clearBubbles();
        clearActive();
        hideOverlay();
        $("#burn-pile").innerHTML = "";
        renderState(ev.state);
        dealHoleCards(ev.players);
        log(ev.text, "hand");
        say(`Hand ${ev.hand_number}. Blinds ${ev.level.small_blind} en ${ev.level.big_blind}, alstublieft.`);
        break;
      case "forced_bet":
        renderState(ev.state);
        log(ev.text);
        break;
      case "hole_cards":
        renderState(ev.state);
        log(ev.text, "me");
        break;
      case "thinking":
        setActive(ev.player);
        break;
      case "action":
        clearActive();
        bubble(ev.player, ev.action);
        if (ev.action.type === "all-in") say(`${ev.player} gaat all-in!`);
        renderState(ev.state);
        log(ev.text, ev.player === t.humanName ? "me" : "");
        if (ev.player === t.humanName) hideActionBar();
        break;
      case "community":
        clearBubbles();
        renderState(ev.state);
        dealBoard(ev.new_cards.length);
        log(ev.text, "street");
        say(`${STREET_NAMES[ev.street] || ev.street}: ${ev.new_cards.join(" ")}`, `${STREET_NAMES[ev.street] || ev.street}: ${cardsWords(ev.new_cards)}.`);
        break;
      case "burn":
        burnCard();
        log(ev.text);
        break;
      case "showdown":
        renderState(ev.state);
        log(ev.text);
        say(`${ev.player} toont ${ev.cards.join(" ")}: ${ev.hand.text}.`, `${ev.player} toont ${cardsWords(ev.cards)}: ${ev.hand.text}.`);
        break;
      case "pot_awarded":
        chipsToWinner(ev.player);
        renderState(ev.state);
        celebrate(ev.player, ev.amount);
        if (ev.reason !== "ongecalld deel terug") say(`${fmt(ev.amount)} voor ${ev.player}.`);
        log(ev.text, "win");
        break;
      case "eliminated":
        renderState(ev.state);
        log(ev.text, "warn");
        if (ev.player === t.humanName) t.eliminatedPlace = ev.place;
        else toast(ev.text);
        say(`${ev.player} is uitgeschakeld op plaats ${ev.place}.`);
        break;
      case "level":
        renderState(ev.state);
        log(ev.text, "hand");
        if (ev.number > 1) {
          toast(`Niveau ${ev.number}: blinds ${ev.level.text}`);
          say(`Nieuw niveau: blinds ${ev.level.small_blind} en ${ev.level.big_blind}.`);
        }
        break;
      case "tournament_finished":
        renderState(ev.state);
        log(ev.text, "win");
        t.tournamentResult = ev;
        say(`Gefeliciteerd, ${ev.winner}!`, `Gefeliciteerd, ${ev.winner}, u wint het toernooi!`, 5000);
        break;
      case "message":
        toast(ev.text);
        log(ev.text, "warn");
        break;
      case "coach":
        coachLine(ev.text);
        break;
      case "decision":
        showDecision(ev);
        say(ev.to_call ? `${t.humanName}, aan u. ${fmt(ev.to_call)} om te callen.` : `${t.humanName}, aan u.`);
        break;
      case "lesson_finished":
        hideActionBar();
        $("#waiting").hidden = true;
        clearActive();
        $("#btn-advice").disabled = true;
        if (ev.outcome !== "quit") showSummary(ev);
        break;
      default:
        break;
    }
  }

  // ---------- sneltoetsen en bediening ----------
  document.addEventListener("keydown", (e) => {
    const t = app.table;
    if (!t || !t.decision || e.target.matches("input, textarea")) return;
    const legal = t.decision.legal;
    const key = e.key.toLowerCase();
    if (key === "f" && !legal.can_check) sendAction("fold");
    else if (key === "c") sendAction(legal.can_check ? "check" : "call");
    else if (key === "k" && legal.can_check) sendAction("check");
    else if (key === "r" && legal.can_raise) sendAction("raise", Number($("#raise-slider").value) || legal.min_raise_to);
    else if (key === "a") sendAction("all-in");
    else if (e.key === "?") askAdvice();
  });

  $("#btn-advice").addEventListener("click", askAdvice);
  $("#btn-voice").addEventListener("click", () => voice.toggle());
  voice.load();
  if (voice.supported) speechSynthesis.onvoiceschanged = () => voice.render();
  $("#btn-home").addEventListener("click", goHome);
  $("#brand").addEventListener("click", goHome);
  $("#speed").addEventListener("input", () => {
    const speed = currentSpeed();
    $("#speed-label").textContent = `${speed}×`;
    if (app.session) api(`/api/sessions/${app.session}/speed`, { speed }).catch(() => {});
  });
  window.addEventListener("beforeunload", () => {
    if (app.session) navigator.sendBeacon(`/api/sessions/${app.session}/quit`, new Blob(["{}"], { type: "application/json" }));
  });

  // ---------- start ----------
  async function init() {
    app.content = await api("/api/content");
    renderHome();
    showScreen("screen-home");
    // Deeplink: ?les=oefenen&naam=Peter start meteen een les.
    const params = new URLSearchParams(location.search);
    if (params.get("naam")) app.name = params.get("naam").trim().slice(0, 16) || "Jij";
    if (app.content.coach.models.some((m) => m.key === params.get("coach"))) app.model = params.get("coach");
    const wanted = app.content.lessons.find((lesson) => lesson.key === params.get("les"));
    if (wanted) startLesson(wanted);
  }
  init().catch((error) => toast(`Kan de server niet bereiken: ${error.message}`, 8000));
})();
