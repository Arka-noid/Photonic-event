"""Feed RSS/Atom (WikiCFP e simili).

Attenzione a una trappola: la data di pubblicazione dell'item è *quando è stata
annunciata* la call, non quando si tiene l'evento. Le date utili stanno nel testo,
quindi qui si ignora `published` e si legge titolo + sommario.
"""

from __future__ import annotations

import re

import feedparser

from ..dateparse import MONTHS, extract_deadlines, parse_range
from .base import Fetcher, make_event, require_url

#: WikiCFP scrive il sommario come "Titolo [Luogo] [Data - Data]". Il luogo è il
#: primo gruppo fra parentesi che non contenga un nome di mese: senza questo si
#: perdeva la città e restava solo la regione dedotta ("asia" al posto di
#: "Qingdao, China").
_BRACKETED = re.compile(r"\[([^\]]{2,80})\]")
_HAS_MONTH = re.compile(r"(?<![a-z])(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")(?![a-z])", re.I)


def extract_location(summary: str | None) -> str | None:
    for candidate in _BRACKETED.findall(summary or ""):
        candidate = " ".join(candidate.split())
        if _HAS_MONTH.search(candidate) or re.fullmatch(r"[\d\s\-–—,./]+", candidate):
            continue          # è la data, non il luogo
        return candidate
    return None


def parse(body: bytes, entry: dict) -> list:
    feed = feedparser.parse(body)
    events = []
    for item in feed.entries:
        title = getattr(item, "title", "") or ""
        summary = getattr(item, "summary", "") or getattr(item, "description", "") or ""
        text = f"{title}. {summary}"
        start, end = parse_range(summary) if summary else (None, None)
        if not start:
            start, end = parse_range(title)
        event = make_event(
            title=title,
            url=getattr(item, "link", "") or entry.get("url", ""),
            # Per un aggregatore il link dell'item è la scheda, non la conferenza:
            # dichiararlo permette al passo di risoluzione di riconoscerlo e al
            # sito di offrirlo come collegamento secondario.
            listing_url=getattr(item, "link", "") if entry.get("is_listing") else "",
            start=start,
            end=end,
            location=getattr(item, "where", None) or extract_location(summary),
            description=summary,
            deadlines=extract_deadlines(text),
            source=entry["id"],
            topics=list(entry.get("topics_default") or []),
        )
        if event:
            events.append(event)
    return events


def handler(entry: dict, fetcher: Fetcher):
    fetched = fetcher.get(require_url(entry), entry.get("fixture"))
    if not fetched.ok:
        return [], fetched
    return parse(fetched.body, entry), fetched
