"""Eventi ricorrenti curati a mano (data/watchlist.yaml).

Serve a coprire il caso più importante e meno automatizzabile: le grandi
conferenze che si tengono ogni anno più o meno nello stesso periodo. Anche
quando nessuno scraper funziona, questa fonte garantisce che CLEO, OFC, ECOC,
NeurIPS eccetera siano comunque sul sito, con il link ufficiale.

Regola di onestà, applicata rigorosamente: un'edizione *attesa* nasce
`unconfirmed` e sull'interfaccia appare come "date da confermare". Diventa
`confirmed` solo se la pagina ufficiale contiene un intervallo di date
dell'anno atteso. Le scadenze si accettano solo quando sono etichettate nel
testo ('abstract deadline: ...'), mai dedotte da una data qualsiasi.
"""

from __future__ import annotations

from datetime import date

import yaml

from ..dateparse import extract_deadlines, parse_range
from ..models import parse_date
from .base import Fetcher, make_event

#: Solo l'inizio della pagina: le date dell'edizione corrente stanno quasi sempre
#: nell'intestazione, mentre più in basso compaiono archivi di edizioni passate.
HEADER_CHARS = 4000


def _expected_edition(item: dict, today: date) -> tuple[date | None, int]:
    """Data attesa della prossima edizione, dal mese tipico dichiarato."""
    month = item.get("typical_month")
    if not month:
        return None, today.year
    year = today.year if month >= today.month else today.year + 1
    try:
        return date(year, int(month), 1), year
    except ValueError:
        return None, year


def _enrich(text: str, expected_year: int) -> tuple[date | None, date | None, dict]:
    """Cerca date confermate nell'intestazione della pagina ufficiale.

    Un intervallo vale come conferma solo se cade nell'anno dell'edizione attesa:
    così l'archivio dell'edizione passata, che spesso resta in pagina, non viene
    scambiato per la prossima.
    """
    header = text[:HEADER_CHARS]
    start, end = parse_range(header)
    if start and start.year != expected_year:
        start, end = None, None
    return start, end, extract_deadlines(text)


def build(items: list, entry: dict, fetcher: Fetcher, today: date | None = None) -> list:
    today = today or date.today()
    events = []
    for item in items or []:
        if item.get("enabled") is False:
            continue
        expected, expected_year = _expected_edition(item, today)
        title = f"{item['name']} {expected_year}" if item.get("append_year", True) else item["name"]
        start, end, deadlines = expected, None, {}
        confidence, precision = "unconfirmed", "month"

        if item.get("url") and entry.get("enrich", True):
            fetched = fetcher.get(item["url"], item.get("fixture"))
            if fetched.ok:
                from bs4 import BeautifulSoup

                text = " ".join(BeautifulSoup(fetched.body, "lxml").get_text(" ", strip=True).split())
                found_start, found_end, deadlines = _enrich(text, expected_year)
                if found_start:
                    start, end = found_start, found_end
                    confidence, precision = "confirmed", "day"

        event = make_event(
            title=title,
            url=item.get("url", ""),
            start=start,
            end=end,
            location=item.get("location"),
            description=item.get("note", ""),
            deadlines=deadlines,
            source=entry["id"],
            topics=list(item.get("topics") or entry.get("topics_default") or []),
            kind=item.get("kind"),
            confidence=confidence,
            date_precision=precision,
            min_score=0,  # la watchlist è curata a mano: la pertinenza è già decisa
        )
        if event:
            if item.get("region"):
                event.region = item["region"]
            events.append(event)
    return events


def handler(entry: dict, fetcher: Fetcher):
    path = fetcher.base_dir / entry.get("path", "data/watchlist.yaml")
    if not path.exists():
        raise FileNotFoundError(f"watchlist non trovata: {path}")
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return build(items, entry, fetcher), None
