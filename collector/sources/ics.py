"""Feed iCalendar. Quando una società pubblica un .ics è la fonte più affidabile
che ci sia: date già strutturate, nessun selettore da indovinare."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from icalendar import Calendar

from ..dateparse import extract_deadlines
from .base import Fetcher, make_event, require_url


def _as_date(value) -> date | None:
    if value is None:
        return None
    value = getattr(value, "dt", value)
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def parse(body: bytes, entry: dict) -> list:
    calendar = Calendar.from_ical(body)
    events = []
    for component in calendar.walk("VEVENT"):
        start = _as_date(component.get("DTSTART"))
        end = _as_date(component.get("DTEND"))
        # In iCalendar DTEND è esclusivo per gli eventi giornalieri: senza questa
        # correzione ogni conferenza risulterebbe lunga un giorno in più.
        if start and end and end > start:
            end = end - timedelta(days=1)
        description = str(component.get("DESCRIPTION") or "")
        event = make_event(
            title=str(component.get("SUMMARY") or ""),
            url=str(component.get("URL") or entry.get("url", "")),
            start=start,
            end=end,
            location=str(component.get("LOCATION") or "") or None,
            description=description,
            deadlines=extract_deadlines(description),
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
