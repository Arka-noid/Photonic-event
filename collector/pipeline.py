"""Orchestrazione: legge il registry, esegue le fonti, fonde i risultati."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml

from .sources import aideadlines, html, ics, llm, rss, watchlist
from .sources.base import Fetcher, SourceResult, run_source

#: Quanto passato recente accettare in ingresso (giorni).
PAST_TOLERANCE_DAYS = 30

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


def collect(registry_path, store, fetcher: Fetcher, today: date):
    """Esegue tutte le fonti e riversa gli eventi nello store. Ritorna (diff, esiti)."""
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
    return diff, results
