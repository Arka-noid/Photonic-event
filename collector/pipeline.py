"""Orchestrazione: legge il registry, esegue le fonti, fonde i risultati."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml

from .links import resolve_official_url
from .sources import aideadlines, html, ics, llm, rss, watchlist
from .sources.base import Fetcher, SourceResult, run_source

#: Quanto passato recente accettare in ingresso (giorni).
PAST_TOLERANCE_DAYS = 30

#: Tetto di risoluzioni per run. Ogni risoluzione è una richiesta HTTP in più,
#: ma si tenta una volta sola per evento: a regime ne restano pochissime.
MAX_LINK_RESOLUTIONS = 40

HANDLERS = {
    "ics": ics.handler,
    "rss": rss.handler,
    "html": html.handler,
    "aideadlines": aideadlines.handler,
    "watchlist": watchlist.handler,
    "llm": llm.handler,
}


def load_registry(path: str | Path) -> list[dict]:
    entries = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    return [e for e in entries if e.get("enabled", True)]


def run_all(entries: list[dict], fetcher: Fetcher) -> list[SourceResult]:
    results = []
    for entry in entries:
        handler = HANDLERS.get(entry.get("type", ""))
        if handler is None:
            result = SourceResult(id=entry.get("id", "?"), name=entry.get("name", "?"))
            result.error = f"tipo di fonte sconosciuto: {entry.get('type')!r}"
            results.append(result)
            continue
        results.append(run_source(entry, handler, fetcher))
    return results


def resolve_links(store, fetcher: Fetcher, limit: int = MAX_LINK_RESOLUTIONS) -> tuple[int, int]:
    """Sostituisce il link della scheda con quello della conferenza, dove riesce.

    Gira DOPO il merge: solo lì si sa quali eventi sono davvero nuovi. Ogni
    evento viene tentato una volta sola — anche se il tentativo fallisce — così
    le richieste non si ripetono a ogni raccolta.

    Ritorna (risolti, tentati).
    """
    pending = [
        e for e in store.events.values()
        if e.listing_url and not e.link_resolved
    ][:limit]

    resolved = 0
    for event in pending:
        event.link_resolved = True          # tentato: non si riprova comunque vada
        try:
            fetched = fetcher.get(event.listing_url)
            if not fetched.ok:
                continue
            official = resolve_official_url(fetched.body, event.listing_url)
        except Exception:                    # una scheda illeggibile non ferma le altre
            continue
        if official:
            event.url = official
            resolved += 1
    return resolved, len(pending)


def collect(registry_path, store, fetcher: Fetcher, today: date):
    """Esegue le fonti, riversa gli eventi, risolve i link delle schede.

    Ritorna (diff, esiti, (link_risolti, link_tentati))."""
    entries = load_registry(registry_path)
    results = run_all(entries, fetcher)
    events = [e for result in results for e in result.events]
    # Gli eventi già conclusi non entrano affatto: altrimenti il digest
    # annuncerebbe come "novità" qualcosa che prune_past rimuove subito dopo.
    cutoff = today - timedelta(days=PAST_TOLERANCE_DAYS)
    events = [e for e in events if not ((e.end or e.start) and (e.end or e.start) < cutoff)]
    # Ordinamento stabile per punteggio: a parità di evento, la versione con più
    # informazioni entra per prima e le successive la arricchiscono.
    events.sort(key=lambda e: (-e.score, e.title.lower()))
    diff = store.upsert_all(events, today)
    # In modalità offline non si tocca la rete: le fixture non hanno schede da aprire.
    links = (0, 0) if fetcher.offline else resolve_links(store, fetcher)
    return diff, results, links
