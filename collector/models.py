"""Modello dati degli eventi e utilità di normalizzazione.

L'identità di un evento è volutamente *fragile in modo prevedibile*: si basa sul
titolo normalizzato e sull'anno. Le fonti sono eterogenee e scrivono lo stesso
evento in dieci modi diversi, quindi la normalizzazione toglie edizione, anno,
sigle di contorno e punteggiatura prima di calcolare l'id.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

KINDS = ("conference", "school", "workshop", "special-session", "other")
TOPICS = ("photonics", "ml", "neuromorphic", "quantum", "biophotonics")
REGIONS = ("europe", "north-america", "asia", "oceania", "africa", "south-america", "online", "unknown")

#: Una data confermata dalla fonte vale più di una dedotta o attesa.
CONFIDENCE_ORDER = {"unconfirmed": 0, "confirmed": 1}

#: Tipi di scadenza riconosciuti, in ordine di urgenza percepita.
DEADLINE_KINDS = ("abstract", "paper", "early-bird", "registration")

DEADLINE_LABELS = {
    "abstract": "abstract",
    "paper": "paper",
    "early-bird": "early bird",
    "registration": "iscrizione",
}

_EDITION_RE = re.compile(r"\b\d{1,3}(st|nd|rd|th)\b")
#: 'NeurIPS (Neural Information Processing Systems)' -> 'NeurIPS'. Le fonti citano
#: lo stesso evento ora con l'acronimo, ora con il nome esteso fra parentesi.
_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ROMAN_RE = re.compile(r"\b[ivxlc]{1,6}\b")
_NOISE_WORDS = {
    "the", "a", "an", "of", "on", "in", "for", "and", "annual", "international",
    "conference", "conf", "symposium", "workshop", "meeting", "edition", "school",
    "summer", "winter", "spring", "autumn", "fall", "congress", "forum", "week",
}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def slugify(text: str) -> str:
    text = strip_accents(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def normalize_title(title: str) -> str:
    """Riduce un titolo alla sua sostanza, per confrontare edizioni diverse.

    'The 25th International Conference on Photonics 2026' -> 'photonics'
    """
    text = strip_accents(title or "").lower()
    # Solo se resta qualcosa fuori: '(Workshop)' come titolo intero va tenuto.
    without_parens = _PARENTHETICAL_RE.sub(" ", text)
    if without_parens.strip():
        text = without_parens
    text = _EDITION_RE.sub(" ", text)
    text = _YEAR_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    words = [w for w in text.split() if w and w not in _NOISE_WORDS and not _ROMAN_RE.fullmatch(w)]
    if not words:  # titolo fatto di sole parole di contorno: meglio tenerlo intero
        words = [w for w in text.split() if w]
    return " ".join(words)


def title_year(title: str, start: date | None) -> str:
    """Anno di riferimento: quello della data d'inizio, o quello scritto nel titolo."""
    if start:
        return str(start.year)
    match = _YEAR_RE.search(title or "")
    return match.group(0) if match else "?"


def stable_id(title: str, start: date | None = None) -> str:
    key = f"{normalize_title(title)}|{title_year(title, start)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def parse_date(value: Any) -> date | None:
    """Accetta date, datetime, stringhe ISO o None. Non indovina formati ambigui."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


@dataclass
class Event:
    """Un evento normalizzato, così come finisce in data/events.json."""

    title: str
    url: str = ""
    kind: str = "conference"
    topics: list[str] = field(default_factory=list)
    start: date | None = None
    end: date | None = None
    location: str | None = None
    region: str = "unknown"
    deadlines: dict[str, date] = field(default_factory=dict)
    source: str = ""
    #: 'confirmed' = date lette da una fonte; 'unconfirmed' = attese, da verificare.
    confidence: str = "confirmed"
    #: 'day' = giorno esatto; 'month' = si conosce solo il mese. Serve a non
    #: mostrare "1 ott 2026" per un evento di cui sappiamo soltanto "in ottobre":
    #: una data dall'aria precisa è una bugia anche se l'etichetta dice "da confermare".
    date_precision: str = "day"
    description: str = ""
    score: int = 0
    first_seen: date | None = None
    last_seen: date | None = None
    #: Numero di run consecutive in cui la fonte non ha più visto l'evento.
    missing_runs: int = 0
    stale: bool = False
    #: Promemoria già inviati, come "abstract@30", per non ripeterli.
    notified: list[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.start = parse_date(self.start)
        self.end = parse_date(self.end)
        self.deadlines = {
            k: d for k, d in ((k, parse_date(v)) for k, v in (self.deadlines or {}).items()) if d
        }
        self.first_seen = parse_date(self.first_seen)
        self.last_seen = parse_date(self.last_seen)
        if self.kind not in KINDS:
            self.kind = "other"
        if self.date_precision not in ("day", "month"):
            self.date_precision = "day"
        if not self.id:
            self.id = stable_id(self.title, self.start)

    # -- ordinamento e query -------------------------------------------------

    @property
    def norm_title(self) -> str:
        return normalize_title(self.title)

    @property
    def year(self) -> str:
        return title_year(self.title, self.start)

    def next_deadline(self, today: date) -> tuple[str, date] | None:
        """La scadenza futura più vicina, o None se sono tutte passate."""
        upcoming = sorted(((k, d) for k, d in self.deadlines.items() if d >= today), key=lambda kv: kv[1])
        return upcoming[0] if upcoming else None

    def is_past(self, today: date) -> bool:
        last = self.end or self.start
        return bool(last and last < today)

    # -- (de)serializzazione -------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "kind": self.kind,
            "topics": sorted(set(self.topics)),
            "start": iso(self.start),
            "end": iso(self.end),
            "location": self.location,
            "region": self.region,
            "deadlines": {k: iso(v) for k, v in sorted(self.deadlines.items())},
            "source": self.source,
            "confidence": self.confidence,
            "date_precision": self.date_precision,
            "description": self.description,
            "score": self.score,
            "first_seen": iso(self.first_seen),
            "last_seen": iso(self.last_seen),
            "missing_runs": self.missing_runs,
            "stale": self.stale,
            "notified": sorted(set(self.notified)),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Event":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})
