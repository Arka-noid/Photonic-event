from datetime import date

import pytest

from collector.deadlines import THRESHOLDS, applicable_threshold, due_reminders, mark_sent
from collector.models import Event


@pytest.mark.parametrize(
    "days_left,expected",
    [(60, None), (31, None), (30, 30), (29, 30), (15, 30), (14, 14), (8, 14), (7, 7), (3, 7), (1, 1), (0, 1)],
)
def test_si_sceglie_sempre_la_soglia_piu_stretta(days_left, expected):
    assert applicable_threshold(days_left) == expected


def test_ogni_soglia_scatta_una_volta_sola():
    event = Event(title="CLEO 2026", deadlines={"abstract": "2026-02-01"})
    inviate = []
    for day in (3, 20, 25, 31):
        reminders = due_reminders([event], date(2026, 1, day))
        inviate += [(r.threshold, r.days_left) for r in reminders]
        mark_sent(reminders)
    assert inviate == [(30, 29), (14, 12), (7, 7), (1, 1)]
    assert due_reminders([event], date(2026, 1, 31)) == []


def test_job_saltato_recupera_con_lurgenza_corretta():
    # Primo contatto a 3 giorni dalla scadenza: deve partire il promemoria da 7,
    # non quello da 30 (che darebbe un'idea sbagliata dell'urgenza).
    event = Event(title="X", deadlines={"paper": "2026-02-01"})
    reminders = due_reminders([event], date(2026, 1, 29))
    assert [(r.threshold, r.days_left) for r in reminders] == [(7, 3)]
    mark_sent(reminders)
    # le soglie più larghe, ormai superate, restano marcate e non riscattano
    assert {"paper@30", "paper@14", "paper@7"} <= set(event.notified)


def test_scadenze_passate_e_eventi_stale_vengono_ignorati():
    passato = Event(title="X", deadlines={"paper": "2026-01-01"})
    assert due_reminders([passato], date(2026, 1, 2)) == []
    stale = Event(title="Y", deadlines={"paper": "2026-02-01"}, stale=True)
    assert due_reminders([stale], date(2026, 1, 29)) == []


def test_ordinamento_per_urgenza():
    lontano = Event(title="Lontano", deadlines={"paper": "2026-01-28"})
    vicino = Event(title="Vicino", deadlines={"abstract": "2026-01-22"})
    reminders = due_reminders([lontano, vicino], date(2026, 1, 21))
    assert [r.event.title for r in reminders] == ["Vicino", "Lontano"]


def test_scadenze_multiple_dello_stesso_evento_sono_indipendenti():
    event = Event(title="X", deadlines={"abstract": "2026-01-25", "registration": "2026-01-28"})
    reminders = due_reminders([event], date(2026, 1, 22))
    assert {r.kind for r in reminders} == {"abstract", "registration"}


def test_le_soglie_sono_ordinate_dalla_piu_larga():
    assert list(THRESHOLDS) == sorted(THRESHOLDS, reverse=True)
