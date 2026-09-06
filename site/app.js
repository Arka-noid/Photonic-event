/* Photonic-event — interfaccia statica su data/events.json.
   Nessuna dipendenza esterna, nessun build step. */
(() => {
  "use strict";

  const MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
  const MONTHS_SHORT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

  const TOPIC_LABELS = {
    photonics: "Fotonica", ml: "Machine learning", neuromorphic: "Neuromorfico",
    quantum: "Quantistica", biophotonics: "Biofotonica",
  };
  const KIND_LABELS = {
    conference: "Conferenze", school: "School", workshop: "Workshop",
    "special-session": "Sessioni speciali", other: "Altro",
  };
  const REGION_LABELS = {
    europe: "Europa", "north-america": "Nord America", asia: "Asia", oceania: "Oceania",
    africa: "Africa", "south-america": "Sud America", online: "Online", unknown: "Sede da definire",
  };
  const DEADLINE_LABELS = {
    abstract: "abstract", paper: "paper", "early-bird": "early bird", registration: "iscrizione",
  };

  const NEW_DAYS = 7;        // finestra del badge "novità"
  const DEADLINE_HORIZON = 60;

  const state = {
    events: [], health: null, generatedAt: null,
    query: "", topic: null, kind: null, region: null, onlyNew: false, includePast: false,
  };

  /* -- utilità date. Le date sono "AAAA-MM-GG" senza fuso: si costruiscono a
        mezzogiorno locale così un fuso negativo non le fa slittare al giorno prima. -- */
  const today = startOfDay(new Date());

  function parseDate(iso) {
    if (!iso) return null;
    const [y, m, d] = iso.split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d, 12);
  }
  function startOfDay(date) { return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 12); }
  function daysBetween(from, to) { return Math.round((to - from) / 86400000); }

  function formatPeriod(event) {
    const start = parseDate(event.start), end = parseDate(event.end);
    if (!start) return "date da definire";
    // Precisione al mese: mostrare "1 ott 2026" darebbe l'idea di un giorno
    // stabilito che in realtà non conosciamo.
    if (event.date_precision === "month") return `${MONTHS[start.getMonth()]} ${start.getFullYear()}`;
    if (!end || +end === +start) return `${start.getDate()} ${MONTHS_SHORT[start.getMonth()]} ${start.getFullYear()}`;
    if (start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear()) {
      return `${start.getDate()}–${end.getDate()} ${MONTHS_SHORT[start.getMonth()]} ${start.getFullYear()}`;
    }
    return `${start.getDate()} ${MONTHS_SHORT[start.getMonth()]} – ${end.getDate()} ${MONTHS_SHORT[end.getMonth()]} ${end.getFullYear()}`;
  }
  function formatDay(date) { return `${date.getDate()} ${MONTHS_SHORT[date.getMonth()]} ${date.getFullYear()}`; }
  function formatCountdown(days) {
    if (days < 0) return "scaduta";
    if (days === 0) return "oggi";
    if (days === 1) return "domani";
    return `fra ${days} giorni`;
  }

  /* -- derivazioni -- */
  function nextDeadline(event) {
    const upcoming = Object.entries(event.deadlines || {})
      .map(([kind, iso]) => ({ kind, date: parseDate(iso) }))
      .filter((d) => d.date && daysBetween(today, d.date) >= 0)
      .sort((a, b) => a.date - b.date);
    return upcoming[0] || null;
  }
  function isPast(event) {
    const last = parseDate(event.end) || parseDate(event.start);
    return Boolean(last && last < today);
  }
  function isNew(event) {
    const seen = parseDate(event.first_seen);
    return Boolean(seen && daysBetween(seen, today) <= NEW_DAYS);
  }

  /* -- filtri -- */
  function matches(event) {
    if (!state.includePast && isPast(event)) return false;
    if (state.topic && !(event.topics || []).includes(state.topic)) return false;
    if (state.kind && event.kind !== state.kind) return false;
    if (state.region === "europe" && event.region !== "europe") return false;
    if (state.onlyNew && !isNew(event)) return false;
    if (state.query) {
      const haystack = [event.title, event.location, event.description, (event.topics || []).join(" ")]
        .filter(Boolean).join(" ").toLowerCase();
      if (!state.query.split(/\s+/).every((word) => haystack.includes(word))) return false;
    }
    return true;
  }

  function sortEvents(list) {
    return list.slice().sort((a, b) => {
      const da = parseDate(a.start), db = parseDate(b.start);
      if (da && db && +da !== +db) return da - db;
      if (da && !db) return -1;
      if (!da && db) return 1;
      // A parità di data l'Europa viene prima: è la scelta di perimetro del progetto.
      const europe = (e) => (e.region === "europe" ? 0 : 1);
      if (europe(a) !== europe(b)) return europe(a) - europe(b);
      return (b.score || 0) - (a.score || 0);
    });
  }

  /* -- rendering -- */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function renderCard(event) {
    const card = el("article", "card" + (isNew(event) ? " is-new" : ""));

    const heading = el("h3");
    if (event.url) {
      const link = el("a", null, event.title);
      link.href = event.url;
      link.rel = "noopener noreferrer";
      link.target = "_blank";
      heading.append(link);
    } else {
      heading.textContent = event.title;
    }
    card.append(heading);

    const meta = el("div", "meta");
    meta.append(el("span", null, formatPeriod(event)));
    const place = event.location || REGION_LABELS[event.region];
    if (place) meta.append(el("span", null, place));
    meta.append(el("span", null, KIND_LABELS[event.kind] || event.kind));
    card.append(meta);

    if (event.description) card.append(el("p", "desc", event.description));

    const badges = el("div", "badges");
    if (isNew(event)) badges.append(el("span", "badge badge-new", "novità"));

    const deadline = nextDeadline(event);
    if (deadline) {
      const left = daysBetween(today, deadline.date);
      const badge = el("span", "badge badge-deadline" + (left <= 14 ? " urgent" : ""),
        `${DEADLINE_LABELS[deadline.kind] || deadline.kind}: ${formatDay(deadline.date)} · ${formatCountdown(left)}`);
      badges.append(badge);
    }
    if (event.confidence === "unconfirmed") {
      badges.append(el("span", "badge badge-unconfirmed", "date da confermare"));
    }
    if (event.stale) badges.append(el("span", "badge badge-stale", "non più vista dalle fonti"));
    for (const topic of event.topics || []) {
      badges.append(el("span", "badge badge-topic", TOPIC_LABELS[topic] || topic));
    }
    if (badges.childElementCount) card.append(badges);
    return card;
  }

  function renderResults(list) {
    const container = document.getElementById("results");
    container.textContent = "";
    if (!list.length) {
      container.append(el("p", "empty", "Nessun evento corrisponde ai filtri."));
      return;
    }
    let currentMonth = "";
    for (const event of list) {
      const start = parseDate(event.start);
      const label = start ? `${MONTHS[start.getMonth()]} ${start.getFullYear()}` : "Date da definire";
      if (label !== currentMonth) {
        currentMonth = label;
        container.append(el("h2", "month", label));
      }
      container.append(renderCard(event));
    }
  }

  function renderDeadlines(list) {
    const section = document.getElementById("deadlines");
    const ul = document.getElementById("deadline-list");
    ul.textContent = "";

    const rows = list
      .map((event) => ({ event, deadline: nextDeadline(event) }))
      .filter((row) => row.deadline && daysBetween(today, row.deadline.date) <= DEADLINE_HORIZON)
      .sort((a, b) => a.deadline.date - b.deadline.date);

    section.hidden = rows.length === 0;
    for (const { event, deadline } of rows) {
      const left = daysBetween(today, deadline.date);
      const li = el("li");
      const label = el("span");
      if (event.url) {
        const link = el("a", null, event.title);
        link.href = event.url;
        link.rel = "noopener noreferrer";
        link.target = "_blank";
        label.append(link);
      } else {
        label.textContent = event.title;
      }
      label.append(document.createTextNode(` — ${DEADLINE_LABELS[deadline.kind] || deadline.kind}`));
      li.append(label, el("span", "when" + (left <= 14 ? " urgent" : ""),
        `${formatDay(deadline.date)} · ${formatCountdown(left)}`));
      ul.append(li);
    }
  }

  function renderChips() {
    const visible = state.events.filter((e) => state.includePast || !isPast(e));
    const countBy = (key, value) => visible.filter((e) =>
      key === "topic" ? (e.topics || []).includes(value) : e[key] === value).length;

    build("filter-topic", Object.keys(TOPIC_LABELS).map((value) => ({
      value, label: TOPIC_LABELS[value], count: countBy("topic", value),
      active: state.topic === value,
      onClick: () => { state.topic = state.topic === value ? null : value; },
    })));

    build("filter-kind", Object.keys(KIND_LABELS).map((value) => ({
      value, label: KIND_LABELS[value], count: countBy("kind", value),
      active: state.kind === value,
      onClick: () => { state.kind = state.kind === value ? null : value; },
    })));

    build("filter-misc", [
      { value: "europe", label: "Solo Europa", count: countBy("region", "europe"),
        active: state.region === "europe",
        onClick: () => { state.region = state.region === "europe" ? null : "europe"; } },
      { value: "new", label: "Novità", count: visible.filter(isNew).length,
        active: state.onlyNew, onClick: () => { state.onlyNew = !state.onlyNew; } },
      { value: "past", label: "Mostra passati", count: state.events.filter(isPast).length,
        active: state.includePast, onClick: () => { state.includePast = !state.includePast; } },
    ]);

    function build(containerId, items) {
      const container = document.getElementById(containerId);
      container.textContent = "";
      for (const item of items) {
        if (!item.count && !item.active) continue;   // niente filtri che non filtrano nulla
        const chip = el("button", "chip");
        chip.type = "button";
        chip.setAttribute("aria-pressed", String(item.active));
        chip.append(document.createTextNode(item.label));
        chip.append(el("span", "count", String(item.count)));
        chip.addEventListener("click", () => { item.onClick(); update(); });
        container.append(chip);
      }
    }
  }

  function renderHealth() {
    const section = document.getElementById("health");
    if (!state.health) { section.hidden = true; return; }
    section.hidden = false;

    const sources = state.health.sources || [];
    const broken = sources.filter((s) => !s.ok);
    document.getElementById("health-summary").textContent =
      `${sources.length - broken.length} di ${sources.length} fonti hanno risposto ` +
      `all'ultimo controllo del ${state.health.checked_at || "?"}.`;

    const ul = document.getElementById("health-list");
    ul.textContent = "";
    for (const source of sources) {
      const li = el("li");
      const cls = !source.ok ? "bad" : source.skipped ? "off" : source.warning ? "warn" : "";
      li.append(el("span", `dot ${cls}`.trim()));
      const body = el("span");
      body.append(el("strong", null, source.name || source.id));
      const note = source.error || source.skipped || source.warning || `${source.n_events} eventi`;
      body.append(el("span", "why", ` — ${note}`));
      li.append(body);
      ul.append(li);
    }
  }

  function update() {
    const list = sortEvents(state.events.filter(matches));
    renderChips();
    renderResults(list);
    renderDeadlines(state.events.filter((e) => !isPast(e)));
    document.getElementById("summary").textContent =
      `${list.length} eventi su ${state.events.length}` +
      (state.includePast ? "" : " (passati esclusi)");
  }

  /* -- tema -- */
  function initTheme() {
    const stored = safeGet("theme");
    if (stored === "dark" || stored === "light") document.documentElement.dataset.theme = stored;
    document.getElementById("theme-toggle").addEventListener("click", () => {
      const dark = document.documentElement.dataset.theme
        ? document.documentElement.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      const next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      safeSet("theme", next);
    });
  }
  // localStorage può lanciare (finestra privata, cookie bloccati): mai far
  // fallire la pagina per una preferenza di tema.
  function safeGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function safeSet(key, value) { try { localStorage.setItem(key, value); } catch { /* ignorato */ } }

  /* -- avvio -- */
  async function load() {
    const [events, health] = await Promise.all([
      fetch("./data/events.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
      fetch("./data/health.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : null).catch(() => null),
    ]);
    state.events = events.events || [];
    state.health = health;
    state.generatedAt = (events.meta || {}).generated_at || null;
    document.getElementById("generated").textContent =
      state.generatedAt ? `Ultimo aggiornamento dei dati: ${state.generatedAt}.` : "";
  }

  document.getElementById("search").addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    update();
  });
  initTheme();

  load().then(() => { update(); renderHealth(); }).catch((error) => {
    document.getElementById("results").append(
      el("p", "empty", "Impossibile caricare i dati degli eventi. " +
        "Se stai aprendo il file in locale, usa `python scripts/preview.py`."));
    console.error("caricamento fallito", error);
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("./sw.js").catch(() => {}));
  }
})();
