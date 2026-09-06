"""Feed RSS/Atom (WikiCFP e simili).

Attenzione a una trappola: la data di pubblicazione dell'item è *quando è stata
annunciata* la call, non quando si tiene l'evento. Le date utili stanno nel testo,
quindi qui si ignora `published` e si legge titolo + sommario.
"""

from __future__ import annotations

import feedparser

from ..dateparse import extract_deadlines, parse_range
from .base import Fetcher, make_event, require_url


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
            start=start,
            end=end,
            location=getattr(item, "where", None),
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
