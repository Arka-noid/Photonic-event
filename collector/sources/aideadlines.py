"""Dataset `conferences.yml` del progetto ai-deadlines.

Verificato in fase di progettazione: il file è raggiungibile e ben strutturato,
ma il mirror pubblico è **fermo al 2025**. Per questo la fonte porta con sé una
guardia di obsolescenza: se l'annata più recente del dataset è precedente
all'anno in corso, lo dichiara in health.json invece di far finta di niente.
"""

from __future__ import annotations

from datetime import date, timedelta

import yaml

from .base import Fetcher, make_event, require_url

#: Quanto indietro nel tempo accettare un evento (serve a tenere il passato recente).
PAST_TOLERANCE = timedelta(days=30)


def parse(body: bytes, entry: dict, today: date | None = None) -> tuple[list, str]:
    today = today or date.today()
    raw = yaml.safe_load(body) or []
    if not isinstance(raw, list):
        raise ValueError("formato inatteso: attesa una lista YAML")

    events = []
    newest_year = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        newest_year = max(newest_year, int(item.get("year") or 0))
        start = item.get("start")
        end = item.get("end")
        deadlines = {}
        if item.get("deadline"):
            deadlines["paper"] = str(item["deadline"])[:10]
        if item.get("abstract_deadline"):
            deadlines["abstract"] = str(item["abstract_deadline"])[:10]

        title = f"{item.get('title', '')} {item.get('year', '')}".strip()
        event = make_event(
            title=title,
            url=item.get("link") or "",
            start=start,
            end=end,
            location=item.get("place"),
            description=item.get("note") or "",
            deadlines=deadlines,
            source=entry["id"],
            topics=list(entry.get("topics_default") or []),
            kind="conference",
        )
        if not event:
            continue
        # Scarta le edizioni vecchie: il dataset è storico e conserva anni di archivio.
        latest = event.end or event.start
        if latest and latest < today - PAST_TOLERANCE:
            continue
        if not latest and not event.deadlines:
            continue
        events.append(event)

    warning = ""
    if newest_year and newest_year < today.year:
        warning = f"dataset fermo al {newest_year}: nessuna edizione {today.year} disponibile"
    return events, warning


def handler(entry: dict, fetcher: Fetcher):
    fetched = fetcher.get(require_url(entry), entry.get("fixture"))
    if not fetched.ok:
        return [], fetched
    events, warning = parse(fetched.body, entry)
    if warning:
        # Passa l'avviso al runner facendo finta di nulla sul piano degli eventi:
        # la fonte ha funzionato, ma il suo contenuto è vecchio e va detto.
        entry["_warning"] = warning
    return events, fetched
