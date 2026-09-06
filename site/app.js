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
    // La scheda dell'aggregatore resta raggiungibile: spesso riporta scadenze e
    // dettagli che il sito ufficiale non espone. Compare solo quando il titolo
    // punta già altrove, altrimenti sarebbe lo stesso link due volte.
    if (event.listing_url && event.listing_url !== event.url) {
      const listing = el("a", "listing-link", "scheda CFP");
      listing.href = event.listing_url;
      listing.rel = "noopener noreferrer";
      listing.target = "_blank";
      meta.append(listing);
    }
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
  function safeRemove(key) { try { localStorage.removeItem(key); } catch { /* ignorato */ } }

  /* -- avvio manuale della raccolta -----------------------------------------
     Il sito è statico: da qui la raccolta si fa partire solo chiedendo a GitHub
     di eseguire il workflow, e l'API vuole un token. Un sito pubblico non ha
     dove custodirlo, quindi si usa quello dell'utente, tenuto in localStorage
     su questo dispositivo e limitato al solo permesso Actions su questo
     repository. Senza token il pulsante resta utile: rimanda alla pagina
     Actions, dove il pulsante "Run workflow" fa la stessa cosa. -- */
  const REPO = "Arka-noid/Photonic-event";
  const API = `https://api.github.com/repos/${REPO}`;
  const WORKFLOW = "collect.yml";
  const PAGES_WORKFLOW = "pages.yml";
  const TOKEN_KEY = "github-token";

  const POLL_MS = 5000;
  const WAIT_RUN_MS = 90000;        // comparsa del run dopo il dispatch
  const WAIT_COLLECT_MS = 900000;   // durata massima della raccolta
  const WAIT_PAGES_MS = 60000;      // comparsa della pubblicazione dopo la raccolta

  const runner = { busy: false, defaultBranch: null };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function status(text, kind) {
    const node = document.getElementById("run-status");
    node.hidden = !text;
    node.textContent = text || "";
    node.className = "run-status" + (kind ? ` ${kind}` : "");
  }

  function setBusy(busy) {
    runner.busy = busy;
    const button = document.getElementById("run-now");
    button.disabled = busy;
    button.classList.toggle("busy", busy);
  }

  async function api(path, options = {}) {
    const response = await fetch(API + path, {
      ...options,
      headers: {
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        Authorization: `Bearer ${safeGet(TOKEN_KEY)}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
    });
    if (!response.ok) {
      const error = new Error(`GitHub ha risposto ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }

  async function latestRunId(workflow, event) {
    const query = `/actions/workflows/${workflow}/runs?per_page=1` + (event ? `&event=${event}` : "");
    const run = ((await api(query)).workflow_runs || [])[0];
    return run ? run.id : 0;
  }

  // Il dispatch non restituisce l'id del run che ha creato. Gli id crescono nel
  // tempo, quindi "il più recente ha un id maggiore di prima" lo identifica
  // senza dipendere dall'orologio del telefono.
  async function waitForNewRun(workflow, event, previousId, timeout, label) {
    const deadline = Date.now() + timeout;
    for (;;) {
      const query = `/actions/workflows/${workflow}/runs?per_page=1` + (event ? `&event=${event}` : "");
      const run = ((await api(query)).workflow_runs || [])[0];
      if (run && run.id > previousId) return run;
      if (Date.now() > deadline) return null;
      status(`${label}…`);
      await sleep(POLL_MS);
    }
  }

  async function waitForCompletion(run, timeout, label) {
    const startedAt = Date.now();
    let current = run;
    while (current.status !== "completed") {
      if (Date.now() - startedAt > timeout) throw new Error(`${label}: sta durando troppo, guarda su GitHub.`);
      status(`${label} (${Math.round((Date.now() - startedAt) / 1000)}s)…`);
      await sleep(POLL_MS);
      current = await api(`/actions/runs/${current.id}`);
    }
    return current;
  }

  async function collectNow() {
    if (runner.busy) return;
    if (navigator.onLine === false) { status("Serve una connessione per avviare la raccolta.", "error"); return; }
    setBusy(true);
    try {
      status("Avvio la raccolta…");
      if (!runner.defaultBranch) runner.defaultBranch = (await api("")).default_branch;

      const beforeCollect = await latestRunId(WORKFLOW, "workflow_dispatch");
      const beforePages = await latestRunId(PAGES_WORKFLOW);

      await api(`/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST",
        body: JSON.stringify({ ref: runner.defaultBranch, inputs: { mode: "collect" } }),
      });

      const started = await waitForNewRun(WORKFLOW, "workflow_dispatch", beforeCollect, WAIT_RUN_MS, "In coda su GitHub");
      if (!started) throw new Error("La raccolta non è comparsa fra le esecuzioni: controlla su GitHub.");

      const collect = await waitForCompletion(started, WAIT_COLLECT_MS, "Raccolta in corso");
      if (collect.conclusion !== "success") throw new Error(`La raccolta è fallita (${collect.conclusion}): guarda il log su GitHub.`);

      // La pubblicazione parte solo se la raccolta ha davvero cambiato i dati:
      // se non compare entro un minuto, non c'era nulla da pubblicare.
      const pages = await waitForNewRun(PAGES_WORKFLOW, null, beforePages, WAIT_PAGES_MS, "Raccolta finita, pubblico il sito");
      if (pages) {
        await waitForCompletion(pages, WAIT_PAGES_MS * 5, "Pubblicazione in corso");
        await sleep(3000);   // il CDN di Pages serve la nuova copia un istante dopo
      }

      const before = new Set(state.events.map((e) => e.id));
      await load();
      update();
      renderHealth();
      const added = state.events.filter((e) => !before.has(e.id)).length;
      status(added
        ? `Aggiornato: ${added} ${added === 1 ? "evento nuovo" : "eventi nuovi"}.`
        : "Raccolta completata: nessun evento nuovo.", "done");
    } catch (error) {
      if (error.status === 401) {
        safeRemove(TOKEN_KEY);
        status("Token rifiutato o scaduto: reinseriscilo.", "error");
        openTokenDialog();
      } else if (error.status === 403) {
        status("Il token non ha il permesso Actions: Read and write su questo repository.", "error");
      } else if (error.status === 404) {
        status("Repository o workflow non raggiungibili con questo token.", "error");
      } else {
        status(error.message || "Avvio fallito.", "error");
      }
      console.error("raccolta manuale fallita", error);
    } finally {
      setBusy(false);
      showForgetToken();
    }
  }

  function openTokenDialog() {
    const dialog = document.getElementById("token-dialog");
    if (typeof dialog.showModal !== "function") {   // browser senza <dialog>
      const typed = window.prompt("Token GitHub (permesso Actions su Photonic-event):");
      if (typed) { safeSet(TOKEN_KEY, typed.trim()); collectNow(); }
      return;
    }
    document.getElementById("token-input").value = "";
    dialog.showModal();
  }

  function showForgetToken() {
    document.getElementById("forget-token").hidden = !safeGet(TOKEN_KEY);
  }

  function initRunner() {
    document.getElementById("run-now").addEventListener("click", () => {
      if (safeGet(TOKEN_KEY)) collectNow(); else openTokenDialog();
    });

    const dialog = document.getElementById("token-dialog");
    dialog.addEventListener("close", () => {
      const typed = document.getElementById("token-input").value.trim();
      document.getElementById("token-input").value = "";
      if (dialog.returnValue !== "save" || !typed) return;
      safeSet(TOKEN_KEY, typed);
      showForgetToken();
      collectNow();
    });

    document.getElementById("forget-token").addEventListener("click", () => {
      safeRemove(TOKEN_KEY);
      showForgetToken();
      status("Token rimosso da questo browser.", "done");
    });

    showForgetToken();
  }

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
  initRunner();

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
