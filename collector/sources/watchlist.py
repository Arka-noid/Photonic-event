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


#: Scarto massimo, in mesi, fra il mese dichiarato nella watchlist e quello
#: trovato in pagina. Le conferenze slittano di qualche settimana, non di stagione.
MONTH_TOLERANCE = 2
#: Una scadenza plausibile non precede l'evento di più di un anno né lo segue.
DEADLINE_MAX_MONTHS_BEFORE = 12


def _months_apart(a: int, b: int) -> int:
    """Distanza fra due mesi trattando l'anno come circolare (dic e gen distano 1)."""
    diff = abs(a - b) % 12
    return min(diff, 12 - diff)


def _plausible_deadlines(found: dict, start: date | None) -> dict:
    """Scarta le scadenze che non possono appartenere a questa edizione.

    Le pagine ufficiali continuano a mostrare le scadenze dell'edizione in corso
    mentre la prossima è già annunciata: senza questo filtro l'iscrizione a ICML
    2027 risultava scaduta a maggio 2026, tredici mesi prima dell'evento.
    """
    if not start:
        return found
    earliest = date(start.year - 1, start.month, 1) if start.month else None
    return {
        kind: due for kind, due in found.items()
        if due <= start and (earliest is None or due >= earliest)
    }


def _enrich(text: str, expected_year: int, expected_month: int | None) -> tuple[date | None, date | None, dict]:
    """Cerca date confermate nell'intestazione della pagina ufficiale.

    Due guardie, entrambe necessarie: l'anno deve essere quello dell'edizione
    attesa **e** il mese deve avvicinarsi a quello dichiarato. Con il solo
    controllo sull'anno, la pagina di SPIE Photonics Europe — che pubblicizza
    Photonics West nell'intestazione — faceva risultare l'evento di aprile come
    tenuto a fine gennaio, per giunta marcato "confermato".
    """
    header = text[:HEADER_CHARS]
    start, end = parse_range(header)
    if start and start.year != expected_year:
        start, end = None, None
    if start and expected_month and _months_apart(start.month, expected_month) > MONTH_TOLERANCE:
        start, end = None, None
    return start, end, _plausible_deadlines(extract_deadlines(text), start)


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
                found_start, found_end, deadlines = _enrich(
                    text, expected_year, item.get("typical_month")
                )
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
