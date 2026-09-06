"""Composizione dei messaggi Telegram: digest delle novità e promemoria."""

from __future__ import annotations

from datetime import date

from .models import DEADLINE_LABELS, Event
from .notify.telegram import esc

KIND_LABELS = {
    "conference": "Conferenze",
    "school": "School",
    "workshop": "Workshop",
    "special-session": "Sessioni speciali",
    "other": "Altro",
}
KIND_ICONS = {"conference": "🎤", "school": "🎓", "workshop": "🛠", "special-session": "📌", "other": "•"}
REGION_LABELS = {
    "europe": "Europa", "north-america": "Nord America", "asia": "Asia",
    "oceania": "Oceania", "africa": "Africa", "south-america": "Sud America",
    "online": "Online", "unknown": "",
}

MONTHS_IT = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")


def fmt_date(value: date | None) -> str:
    return f"{value.day} {MONTHS_IT[value.month - 1]} {value.year}" if value else ""


MONTHS_IT_FULL = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")


def fmt_period(event: Event) -> str:
    if not event.start:
        return "date da definire"
    if event.date_precision == "month":
        # Sappiamo solo il mese: dirlo, invece di spacciare il primo del mese
        # per una data reale.
        return f"{MONTHS_IT_FULL[event.start.month - 1]} {event.start.year}"
    if not event.end or event.end == event.start:
        return fmt_date(event.start)
    if (event.start.year, event.start.month) == (event.end.year, event.end.month):
        return f"{event.start.day}–{event.end.day} {MONTHS_IT[event.start.month - 1]} {event.start.year}"
    return f"{fmt_date(event.start)} – {fmt_date(event.end)}"


def fmt_days(days: int) -> str:
    if days == 0:
        return "oggi"
    if days == 1:
        return "domani"
    return f"fra {days} giorni"


def event_line(event: Event, today: date) -> str:
    """Una voce del digest: titolo linkato, periodo, luogo, prossima scadenza."""
    title = esc(event.title)
    head = f'<a href="{esc(event.url)}">{title}</a>' if event.url else f"<b>{title}</b>"

    bits = [fmt_period(event)]
    if event.confidence == "unconfirmed":
        bits[0] += " (da confermare)"
    place = event.location or REGION_LABELS.get(event.region, "")
    if place:
        bits.append(esc(place))

    line = f"{KIND_ICONS.get(event.kind, '•')} {head}\n   {esc(' · '.join(b for b in bits if b))}"

    upcoming = event.next_deadline(today)
    if upcoming:
        kind, due = upcoming
        label = DEADLINE_LABELS.get(kind, kind)
        line += f"\n   ⏳ {esc(label)}: {fmt_date(due)} ({fmt_days((due - today).days)})"
    return line


def _health_footer(results) -> str:
    """Riga finale sullo stato delle fonti. Il silenzio su una fonte rotta sarebbe
    la cosa peggiore che questo sistema possa fare, quindi si dice sempre."""
    if not results:
        return ""
    broken = [r for r in results if not r.ok]
    skipped = [r for r in results if r.ok and r.skipped]
    empty = [r for r in results if r.ok and not r.skipped and r.n_events == 0]

    parts = [f"{len(results) - len(broken) - len(skipped)}/{len(results) - len(skipped)} fonti ok"]
    if broken:
        parts.append("non raggiungibili: " + ", ".join(esc(r.id) for r in broken))
    if empty:
        parts.append("zero risultati: " + ", ".join(esc(r.id) for r in empty))
    return "\n\n<i>🩺 " + " · ".join(parts) + "</i>"


def build_digest(diff, results, today: date) -> str | None:
    """Il messaggio delle novità. None se non c'è nulla da dire.

    Le fonti rotte da sole non fanno scattare un messaggio: sarebbero rumore
    ricorrente. Compaiono in coda quando c'è già qualcosa da comunicare, e
    restano comunque sempre visibili sul sito.
    """
    if not diff:
        return None

    sections: list[str] = [f"<b>📡 Photonic-event — {fmt_date(today)}</b>"]

    if diff.new:
        by_kind: dict[str, list[Event]] = {}
        for event in sorted(diff.new, key=lambda e: (-e.score, e.start or date.max)):
            by_kind.setdefault(event.kind, []).append(event)
        sections.append(f"\n<b>Nuovi eventi ({len(diff.new)})</b>")
        for kind in ("conference", "school", "workshop", "special-session", "other"):
            group = by_kind.get(kind)
            if not group:
                continue
            sections.append(f"\n<u>{KIND_LABELS[kind]}</u>")
            sections.extend(event_line(e, today) for e in group)

    if diff.updated:
        changed_dates = [
            (event, changes) for event, changes in diff.updated
            if any(c.startswith("deadline") or c in ("start", "end") for c in changes)
        ]
        if changed_dates:
            sections.append(f"\n<b>Date aggiornate ({len(changed_dates)})</b>")
            for event, changes in changed_dates[:15]:
                what = ", ".join(esc(c.replace("deadline:", "scadenza ")) for c in changes)
                sections.append(f"{event_line(event, today)}\n   🔄 {what}")

    return "\n".join(sections) + _health_footer(results)


def build_reminders(reminders, today: date) -> str | None:
    """Il messaggio dei promemoria scadenze."""
    if not reminders:
        return None
    lines = [f"<b>⏰ Scadenze in arrivo — {fmt_date(today)}</b>", ""]
    for reminder in reminders:
        event = reminder.event
        title = esc(event.title)
        head = f'<a href="{esc(event.url)}">{title}</a>' if event.url else f"<b>{title}</b>"
        lines.append(
            f"• {head}\n"
            f"   {esc(reminder.label)}: <b>{fmt_date(reminder.due)}</b> — {fmt_days(reminder.days_left)}"
        )
    return "\n".join(lines)
