"""Promemoria delle scadenze.

Ogni coppia (evento, tipo di scadenza, soglia) viene notificata una sola volta:
la traccia sta in `Event.notified` come "abstract@30", che viene committata
insieme agli eventi. Se una scadenza viene spostata, `store.merge_event` ripulisce
le tracce di quel tipo e i promemoria ripartono — comportamento voluto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import DEADLINE_LABELS, Event

#: Giorni di anticipo. Il T-1 è l'ultimo appello, il T-30 serve a organizzarsi.
THRESHOLDS = (30, 14, 7, 1)


@dataclass
class Reminder:
    event: Event
    kind: str          # 'abstract', 'paper', ...
    due: date
    days_left: int
    threshold: int

    @property
    def token(self) -> str:
        return f"{self.kind}@{self.threshold}"

    @property
    def label(self) -> str:
        return DEADLINE_LABELS.get(self.kind, self.kind)


def applicable_threshold(days_left: int) -> int | None:
    """La soglia più stretta in cui ricade `days_left`.

    A 3 giorni dalla scadenza il promemoria giusto è quello da 7, non quello da 30:
    se un job è saltato si recupera, ma con l'urgenza corretta.
    """
    candidates = [t for t in THRESHOLDS if days_left <= t]
    return min(candidates) if candidates else None


def due_reminders(events, today: date) -> list[Reminder]:
    """Promemoria da inviare oggi, ordinati per urgenza."""
    out: list[Reminder] = []
    for event in events:
        if event.stale:
            continue
        for kind, due in event.deadlines.items():
            if not due or due < today:
                continue
            days_left = (due - today).days
            threshold = applicable_threshold(days_left)
            if threshold is None:
                continue
            if f"{kind}@{threshold}" in event.notified:
                continue
            out.append(Reminder(event, kind, due, days_left, threshold))
    out.sort(key=lambda r: (r.days_left, r.event.title.lower()))
    return out


def mark_sent(reminders) -> None:
    """Segna la soglia inviata **e tutte quelle più larghe**.

    Senza questo, un promemoria inviato in ritardo a T-3 (soglia 7) lascerebbe
    'abstract@30' e 'abstract@14' non marcati: scaduti ormai, non scatterebbero
    mai più, ma resterebbero a sporcare lo stato. Marcarli tiene il file onesto.
    """
    for reminder in reminders:
        for threshold in THRESHOLDS:
            if threshold >= reminder.threshold:
                token = f"{reminder.kind}@{threshold}"
                if token not in reminder.event.notified:
                    reminder.event.notified.append(token)
