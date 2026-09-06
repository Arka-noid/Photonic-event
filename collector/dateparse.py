"""Estrazione di date e intervalli da testo libero.

I siti di conferenze scrivono le date in ogni modo immaginabile
('10–15 May 2026', 'May 10-15, 2026', '10 May – 15 June 2026'). Qui si coprono
le forme con il mese scritto a parole e quelle ISO, che insieme sono la larga
maggioranza dei casi in inglese.

Scelta deliberata: i formati puramente numerici ambigui (10/05/2026) vengono
**rifiutati**, non indovinati. Sbagliare mese e giorno significa mandare un
promemoria per la scadenza sbagliata, che è peggio che non mandarlo.
"""

from __future__ import annotations

import re
from datetime import date

MONTHS = {
    "jan": 1, "january": 1, "gen": 1, "gennaio": 1,
    "feb": 2, "february": 2, "febbraio": 2,
    "mar": 3, "march": 3, "marzo": 3,
    "apr": 4, "april": 4, "aprile": 4,
    "may": 5, "maggio": 5,
    "jun": 6, "june": 6, "giu": 6, "giugno": 6,
    "jul": 7, "july": 7, "lug": 7, "luglio": 7,
    "aug": 8, "august": 8, "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "september": 9, "set": 9, "settembre": 9,
    "oct": 10, "october": 10, "ott": 10, "ottobre": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "december": 12, "dic": 12, "dicembre": 12,
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_DASH = r"[-–—]|\bto\b|\bal\b"

# 10-15 May 2026  /  10 - 15 maggio 2026
_RANGE_DAY_FIRST = re.compile(
    rf"\b(?P<d1>\d{{1,2}})\s*(?:{_DASH})\s*(?P<d2>\d{{1,2}})\s+(?P<month>{_MONTH_RE})\.?,?\s+(?P<year>\d{{4}})\b",
    re.I,
)
# May 10-15, 2026
_RANGE_MONTH_FIRST = re.compile(
    rf"\b(?P<month>{_MONTH_RE})\.?\s+(?P<d1>\d{{1,2}})\s*(?:{_DASH})\s*(?P<d2>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b",
    re.I,
)
# 10 May - 15 June 2026  /  May 10 - June 15, 2026
_RANGE_CROSS_MONTH = re.compile(
    rf"\b(?:(?P<d1>\d{{1,2}})\s+(?P<m1>{_MONTH_RE})|(?P<m1b>{_MONTH_RE})\.?\s+(?P<d1b>\d{{1,2}}))"
    rf"\.?,?\s*(?:{_DASH})\s*"
    rf"(?:(?P<d2>\d{{1,2}})\s+(?P<m2>{_MONTH_RE})|(?P<m2b>{_MONTH_RE})\.?\s+(?P<d2b>\d{{1,2}}))"
    rf"\.?,?\s+(?P<year>\d{{4}})\b",
    re.I,
)
# 10 May 2026  /  May 10, 2026
_SINGLE_DAY_FIRST = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{_MONTH_RE})\.?,?\s+(?P<year>\d{{4}})\b", re.I
)
_SINGLE_MONTH_FIRST = re.compile(
    rf"\b(?P<month>{_MONTH_RE})\.?\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b", re.I
)
_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
# May 2026 (senza giorno): utile per gli eventi 'attesi' della watchlist
_MONTH_YEAR = re.compile(rf"\b(?P<month>{_MONTH_RE})\.?\s+(?P<year>\d{{4}})\b", re.I)


def _make(year, month, day) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        return None


def _month_num(name: str | None) -> int | None:
    return MONTHS.get(name.lower().rstrip("."), None) if name else None


def parse_range(text: str | None) -> tuple[date | None, date | None]:
    """Ritorna (inizio, fine). `fine` è None per una data singola."""
    if not text:
        return None, None
    text = " ".join(str(text).split())

    match = _ISO.search(text)
    if match:
        start = _make(match["year"], match["month"], match["day"])
        rest = text[match.end():]
        second = _ISO.search(rest)
        end = _make(second["year"], second["month"], second["day"]) if second else None
        if start:
            return start, (end if end and end >= start else None)

    match = _RANGE_CROSS_MONTH.search(text)
    if match:
        m1 = _month_num(match["m1"] or match["m1b"])
        m2 = _month_num(match["m2"] or match["m2b"])
        d1 = match["d1"] or match["d1b"]
        d2 = match["d2"] or match["d2b"]
        start, end = _make(match["year"], m1, d1), _make(match["year"], m2, d2)
        if start and end and end >= start:
            return start, end

    for pattern in (_RANGE_DAY_FIRST, _RANGE_MONTH_FIRST):
        match = pattern.search(text)
        if match:
            month = _month_num(match["month"])
            start, end = _make(match["year"], month, match["d1"]), _make(match["year"], month, match["d2"])
            if start and end and end >= start:
                return start, end
            if start:
                return start, None

    for pattern in (_SINGLE_DAY_FIRST, _SINGLE_MONTH_FIRST):
        match = pattern.search(text)
        if match:
            start = _make(match["year"], _month_num(match["month"]), match["day"])
            if start:
                return start, None

    return None, None


def parse_month_year(text: str | None) -> date | None:
    """Solo mese e anno -> primo del mese. Il chiamante deve marcarlo 'unconfirmed'."""
    if not text:
        return None
    match = _MONTH_YEAR.search(" ".join(str(text).split()))
    if not match:
        return None
    return _make(match["year"], _month_num(match["month"]), 1)


#: Etichette con cui i siti annunciano una scadenza -> tipo interno.
#: L'ordine conta: si va dalla più specifica alla più generica, perché le
#: etichette si contengono a vicenda ('early-bird registration' contiene
#: 'registration', 'abstract submission' contiene 'submission').
DEADLINE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("early-bird", r"early[-\s](?:bird|registration)(?:\s+registration)?(?:\s+(?:deadline|closes|ends|due))?"),
    ("abstract", r"abstract[a-z]*(?:\s+(?:submission|deadline|due|closes))*"),
    ("paper", r"(?:full[-\s])?(?:paper|manuscript)[a-z]*(?:\s+(?:submission|deadline|due|closes))*"),
    ("registration", r"registration(?:\s+(?:deadline|closes|due))?"),
)

#: Quanto lontano dall'etichetta si accetta la data. Abbastanza per attraversare
#: 'submission deadline —', poco per non agganciare la frase successiva.
_DEADLINE_WINDOW = 80


def extract_deadlines(text: str | None) -> dict[str, date]:
    """Trova 'Abstract deadline: 15 January 2026' e simili nel testo.

    Ogni porzione di testo consumata da un'etichetta (etichetta + data) viene
    mascherata, così la stessa data non può essere attribuita a due scadenze
    diverse: senza questo, 'Abstract submission deadline: X' finiva anche come
    scadenza 'paper', e 'early-bird registration' veniva contata due volte.
    """
    if not text:
        return {}
    flat = " ".join(str(text).split())
    consumed = [False] * len(flat)
    found: dict[str, date] = {}

    for kind, label in DEADLINE_PATTERNS:
        for match in re.finditer(label, flat, re.I):
            if any(consumed[match.start():match.end()]):
                continue
            window = flat[match.end(): match.end() + _DEADLINE_WINDOW]
            parsed, _ = parse_range(window)
            if not parsed:
                continue
            found[kind] = parsed
            # Maschera etichetta + finestra fino alla data inclusa.
            date_match = re.search(r"\d{1,2}[^,]{0,20}\d{4}|\d{4}-\d{2}-\d{2}", window)
            end = match.end() + (date_match.end() if date_match else _DEADLINE_WINDOW)
            for i in range(match.start(), min(end, len(flat))):
                consumed[i] = True
            break  # la prima occorrenza è quella dell'edizione corrente
    return found
