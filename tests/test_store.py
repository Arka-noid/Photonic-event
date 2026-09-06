from datetime import date

from collector.models import Event
from collector.store import STALE_AFTER_MISSING_RUNS, Store


def test_watchlist_senza_data_e_fonte_datata_si_fondono(tmp_path):
    # È il caso che genererebbe doppioni: l'id dipende dall'anno, e un evento
    # visto prima senza data e poi con data cambierebbe id.
    store = Store(tmp_path / "events.json")
    store.upsert_all([Event(title="CLEO", confidence="unconfirmed", source="watchlist")], date(2026, 1, 1))
    diff = store.upsert_all(
        [Event(title="CLEO 2026", start="2026-05-10", deadlines={"abstract": "2026-01-20"}, source="optica")],
        date(2026, 1, 2),
    )
    assert len(store.events) == 1
    assert not diff.new
    event = next(iter(store.events.values()))
    assert event.first_seen == date(2026, 1, 1)   # mai sovrascritto
    assert event.start == date(2026, 5, 10)
    assert event.confidence == "confirmed"
    assert "optica" in event.source and "watchlist" in event.source


def test_una_fonte_unconfirmed_non_sovrascrive_date_confermate(tmp_path):
    store = Store(tmp_path / "events.json")
    store.upsert_all([Event(title="X 2026", start="2026-05-10", source="a")], date(2026, 1, 1))
    store.upsert_all(
        [Event(title="X 2026", start="2026-09-09", confidence="unconfirmed", source="llm")], date(2026, 1, 2)
    )
    assert next(iter(store.events.values())).start == date(2026, 5, 10)


def test_scadenza_spostata_riattiva_i_promemoria(tmp_path):
    store = Store(tmp_path / "events.json")
    store.upsert_all([Event(title="X 2026", deadlines={"abstract": "2026-02-01"}, source="a")], date(2026, 1, 1))
    event = next(iter(store.events.values()))
    event.notified = ["abstract@30", "abstract@14"]
    store.upsert_all([Event(title="X 2026", deadlines={"abstract": "2026-03-01"}, source="a")], date(2026, 1, 2))
    assert event.notified == []
    assert event.deadlines["abstract"] == date(2026, 3, 1)


def test_evento_sparito_diventa_stale_ma_non_viene_cancellato(tmp_path):
    store = Store(tmp_path / "events.json")
    store.upsert_all([Event(title="X 2026", start="2026-05-10", source="a")], date(2026, 1, 1))
    for i in range(STALE_AFTER_MISSING_RUNS):
        store.upsert_all([], date(2026, 1, 2 + i))
    event = next(iter(store.events.values()))
    assert event.stale and len(store.events) == 1


def test_prune_rimuove_solo_il_passato_remoto(tmp_path):
    store = Store(tmp_path / "events.json")
    store.upsert_all(
        [Event(title="Vecchio 2020", start="2020-01-01", end="2020-01-02", source="a"),
         Event(title="Recente 2026", start="2026-08-01", end="2026-08-02", source="a")],
        date(2026, 9, 1),
    )
    assert store.prune_past(date(2026, 9, 1), keep_days=120) == 1
    assert len(store.events) == 1


def test_salvataggio_e_ricarica_conservano_lo_stato(tmp_path):
    path = tmp_path / "events.json"
    store = Store(path)
    store.upsert_all([Event(title="X 2026", start="2026-05-10", source="a", notified=["abstract@30"])], date(2026, 1, 1))
    store.save(date(2026, 1, 1))

    reloaded = Store(path).load()
    assert len(reloaded.events) == 1
    event = next(iter(reloaded.events.values()))
    assert event.first_seen == date(2026, 1, 1) and event.notified == ["abstract@30"]


def test_una_data_esatta_sostituisce_quella_nota_solo_al_mese(tmp_path):
    store = Store(tmp_path / "events.json")
    store.upsert_all(
        [Event(title="ECOC 2026", start="2026-09-01", confidence="unconfirmed",
               date_precision="month", source="watchlist")],
        date(2026, 1, 1),
    )
    store.upsert_all(
        [Event(title="ECOC 2026", start="2026-09-14", end="2026-09-18", source="ecoc")], date(2026, 1, 2)
    )
    event = next(iter(store.events.values()))
    assert event.date_precision == "day"
    assert (event.start, event.end) == (date(2026, 9, 14), date(2026, 9, 18))
