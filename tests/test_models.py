from datetime import date

from collector.models import Event, normalize_title, stable_id


def test_normalize_toglie_edizione_anno_e_parole_di_contorno():
    assert normalize_title("The 25th International Conference on Photonics 2026") == "photonics"
    assert normalize_title("Photonics") == "photonics"


def test_stesso_evento_scritto_diversamente_ha_lo_stesso_id():
    assert stable_id("CLEO 2026") == stable_id("CLEO", date(2026, 5, 10))
    assert stable_id("The 3rd Workshop on Optics 2026") == stable_id("Workshop on Optics", date(2026, 1, 1))


def test_edizioni_di_anni_diversi_sono_eventi_diversi():
    assert stable_id("CLEO 2026") != stable_id("CLEO 2027")


def test_titolo_di_sole_parole_di_contorno_non_collassa_a_vuoto():
    # 'International Conference' non deve ridursi a stringa vuota e collidere
    # con qualunque altro titolo altrettanto generico.
    assert normalize_title("International Conference") != ""


def test_deadline_nulle_vengono_scartate_e_le_date_normalizzate():
    event = Event(title="X", start="2026-05-10", deadlines={"abstract": "2026-01-01", "paper": None})
    assert event.start == date(2026, 5, 10)
    assert event.deadlines == {"abstract": date(2026, 1, 1)}


def test_prossima_scadenza_ignora_quelle_passate():
    event = Event(title="X", deadlines={"abstract": "2026-01-01", "paper": "2026-03-01"})
    assert event.next_deadline(date(2026, 2, 1)) == ("paper", date(2026, 3, 1))
    assert event.next_deadline(date(2026, 4, 1)) is None


def test_roundtrip_serializzazione():
    original = Event(
        title="Photonic AI 2026", url="https://x.test", start="2026-05-10", end="2026-05-12",
        deadlines={"abstract": "2026-01-15"}, topics=["photonics"], location="Milan, Italy",
        first_seen="2026-01-01", last_seen="2026-01-02", notified=["abstract@30"],
    )
    restored = Event.from_dict(original.to_dict())
    assert restored.to_dict() == original.to_dict()


def test_kind_sconosciuto_ricade_su_other():
    assert Event(title="X", kind="banchetto").kind == "other"


def test_is_past_usa_la_data_di_fine():
    event = Event(title="X", start="2026-05-10", end="2026-05-14")
    assert not event.is_past(date(2026, 5, 12))
    assert event.is_past(date(2026, 5, 15))


def test_acronimo_ed_espansione_fra_parentesi_sono_lo_stesso_evento():
    # La watchlist scrive 'NeurIPS (Neural Information Processing Systems)',
    # ai-deadlines scrive 'NEURIPS': senza questa regola sono due voci distinte.
    assert stable_id("NeurIPS (Neural Information Processing Systems) 2026") == stable_id("NEURIPS 2026")


def test_titolo_fatto_di_sole_parentesi_non_si_svuota():
    assert normalize_title("(Workshop)") == "workshop"
