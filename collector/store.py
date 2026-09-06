"""Persistenza degli eventi e calcolo delle novità fra una run e l'altra.

Due principi:

1. `first_seen` non si tocca mai una volta scritto: è ciò che rende sensato il
   badge "novità" e il digest.
2. Un evento che sparisce da una fonte non viene cancellato. Le fonti sono
   inaffidabili (un selettore rotto svuota una pagina intera), quindi l'assenza
   viene contata e, oltre soglia, marcata `stale` — mai interpretata come
   "evento annullato".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from .models import CONFIDENCE_ORDER, Event, iso, normalize_title, parse_date

#: Run consecutive senza avvistamenti prima di marcare un evento come 'stale'.
STALE_AFTER_MISSING_RUNS = 3


@dataclass
class Diff:
    """Cosa è cambiato in questa run: è la materia prima del digest Telegram."""

    new: list[Event] = field(default_factory=list)
    updated: list[tuple[Event, list[str]]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.new or self.updated)


def _match_key(event: Event) -> tuple[str, str]:
    return (event.norm_title, event.year)


def _better(candidate: Event, existing: Event) -> bool:
    """La nuova versione di un campo vince solo se non è un peggioramento."""
    return CONFIDENCE_ORDER.get(candidate.confidence, 0) >= CONFIDENCE_ORDER.get(existing.confidence, 0)


def find_match(event: Event, index: dict[str, Event]) -> Event | None:
    """Trova l'evento già noto corrispondente.

    Prima per id esatto, poi per (titolo normalizzato, anno). Il secondo passaggio
    serve perché un evento visto senza data e poi con data cambia id: senza questo
    si creerebbe un doppione a ogni conferma di calendario.
    """
    if event.id in index:
        return index[event.id]
    key = _match_key(event)
    for known in index.values():
        if _match_key(known) == key:
            return known
        # Un lato senza anno ('?') combacia con lo stesso titolo datato.
        if known.norm_title == event.norm_title and "?" in (known.year, event.year):
            return known
    return None


def merge_event(existing: Event, incoming: Event, today: date) -> list[str]:
    """Fonde `incoming` dentro `existing`. Ritorna i campi cambiati in modo notevole."""
    changed: list[str] = []

    for attr in ("start", "end"):
        new_value = getattr(incoming, attr)
        old_value = getattr(existing, attr)
        if new_value and new_value != old_value and _better(incoming, existing):
            setattr(existing, attr, new_value)
            changed.append(attr)
    # Un giorno esatto sostituisce sempre un "sappiamo solo il mese".
    if incoming.start and incoming.date_precision == "day" and existing.date_precision == "month":
        existing.date_precision = "day"

    for kind, new_date in incoming.deadlines.items():
        old_date = existing.deadlines.get(kind)
        if new_date and new_date != old_date and _better(incoming, existing):
            existing.deadlines[kind] = new_date
            changed.append(f"deadline:{kind}")
            # Una scadenza spostata deve poter riattivare i promemoria già inviati.
            existing.notified = [n for n in existing.notified if not n.startswith(f"{kind}@")]

    # Campi descrittivi: si riempiono se mancano, senza generare "aggiornamenti"
    # rumorosi nel digest.
    for attr in ("url", "listing_url", "location", "description"):
        if not getattr(existing, attr) and getattr(incoming, attr):
            setattr(existing, attr, getattr(incoming, attr))
    # Il link risolto non va perso: la fonte lo riporta grezzo a ogni giro, e
    # senza questo l'evento tornerebbe a puntare alla scheda dopo ogni raccolta.
    existing.link_resolved = existing.link_resolved or incoming.link_resolved
    if existing.region in ("unknown", "") and incoming.region not in ("unknown", ""):
        existing.region = incoming.region
    if incoming.topics:
        existing.topics = sorted(set(existing.topics) | set(incoming.topics))
    if incoming.score > existing.score:
        existing.score = incoming.score
    if CONFIDENCE_ORDER.get(incoming.confidence, 0) > CONFIDENCE_ORDER.get(existing.confidence, 0):
        existing.confidence = incoming.confidence
        changed.append("confidence")
    if incoming.source and incoming.source not in existing.source.split(","):
        existing.source = ",".join(filter(None, [existing.source, incoming.source]))

    existing.last_seen = today
    existing.missing_runs = 0
    existing.stale = False
    return changed


class Store:
    """Il file data/events.json, con le operazioni che ci servono sopra."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.events: dict[str, Event] = {}
        self.meta: dict = {}

    # -- I/O -----------------------------------------------------------------

    def load(self) -> "Store":
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            self.meta = raw.get("meta", {})
            for item in raw.get("events", []):
                event = Event.from_dict(item)
                self.events[event.id] = event
        return self

    def save(self, today: date | None = None) -> None:
        ordered = sorted(
            self.events.values(),
            key=lambda e: (e.start or date.max, -e.score, e.title.lower()),
        )
        payload = {
            "meta": {**self.meta, "generated_at": iso(today or date.today()), "count": len(ordered)},
            "events": [e.to_dict() for e in ordered],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # -- operazioni ----------------------------------------------------------

    def upsert_all(self, incoming: Iterable[Event], today: date) -> Diff:
        diff = Diff()
        seen_ids: set[str] = set()

        for event in incoming:
            match = find_match(event, self.events)
            if match is None:
                event.first_seen = event.first_seen or today
                event.last_seen = today
                event.missing_runs = 0
                self.events[event.id] = event
                diff.new.append(event)
                seen_ids.add(event.id)
                continue

            changed = merge_event(match, event, today)
            seen_ids.add(match.id)
            if changed:
                diff.updated.append((match, changed))

        self._age_unseen(seen_ids)
        return diff

    def _age_unseen(self, seen_ids: set[str]) -> None:
        for event in self.events.values():
            if event.id in seen_ids:
                continue
            event.missing_runs += 1
            if event.missing_runs >= STALE_AFTER_MISSING_RUNS:
                event.stale = True

    def prune_past(self, today: date, keep_days: int = 120) -> int:
        """Rimuove gli eventi finiti da più di `keep_days`. Il passato recente resta
        visibile: serve a capire cosa ci si è persi."""
        cutoff = today.toordinal() - keep_days
        removed = [
            e.id for e in self.events.values()
            if (e.end or e.start) and (e.end or e.start).toordinal() < cutoff
        ]
        for event_id in removed:
            del self.events[event_id]
        return len(removed)

    def upcoming(self, today: date) -> list[Event]:
        return [e for e in self.events.values() if not e.is_past(today)]


def write_health(path: str | Path, results: list[dict], today: date) -> None:
    """Stato per fonte dell'ultima run — mostrato sul sito e riassunto nel digest."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at": iso(today),
        "ok": sum(1 for r in results if r.get("ok")),
        "total": len(results),
        "sources": results,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
