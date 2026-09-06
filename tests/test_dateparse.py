from datetime import date

import pytest

from collector.dateparse import extract_deadlines, parse_month_year, parse_range


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10-15 May 2026", (date(2026, 5, 10), date(2026, 5, 15))),
        ("May 10-15, 2026", (date(2026, 5, 10), date(2026, 5, 15))),
        ("10 May – 15 June 2026", (date(2026, 5, 10), date(2026, 6, 15))),
        ("May 10 - June 15, 2026", (date(2026, 5, 10), date(2026, 6, 15))),
        ("15 January 2026", (date(2026, 1, 15), None)),
        ("Jan 15, 2026", (date(2026, 1, 15), None)),
        ("2026-05-10", (date(2026, 5, 10), None)),
        ("2026-05-10 / 2026-05-15", (date(2026, 5, 10), date(2026, 5, 15))),
        ("Conference held 3 to 7 September 2026", (date(2026, 9, 3), date(2026, 9, 7))),
    ],
)
def test_intervalli_riconosciuti(text, expected):
    assert parse_range(text) == expected


@pytest.mark.parametrize("text", ["10/05/2026", "05.10.2026", "prossimamente", "", None])
def test_formati_ambigui_o_vuoti_vengono_rifiutati(text):
    # Meglio nessuna data che una data sbagliata: un giorno/mese invertito
    # significherebbe un promemoria per la scadenza sbagliata.
    assert parse_range(text) == (None, None)


def test_mese_e_anno_soli_danno_il_primo_del_mese():
    assert parse_month_year("Conference held in May 2027") == date(2027, 5, 1)
    assert parse_month_year("nessuna data") is None


def test_scadenze_etichettate_non_si_rubano_la_data_a_vicenda():
    found = extract_deadlines(
        "Abstract submission deadline: 15 January 2026. "
        "Early-bird registration until 1 March 2026. Paper due 20 Feb 2026"
    )
    assert found == {
        "abstract": date(2026, 1, 15),
        "early-bird": date(2026, 3, 1),
        "paper": date(2026, 2, 20),
    }


def test_abstract_submission_non_diventa_anche_scadenza_paper():
    found = extract_deadlines("Abstract submission deadline: 15 January 2026")
    assert found == {"abstract": date(2026, 1, 15)}


def test_early_bird_registration_non_viene_contata_due_volte():
    found = extract_deadlines("Early-bird registration closes 1 March 2026")
    assert set(found) == {"early-bird"}


def test_testo_senza_date_non_produce_scadenze():
    assert extract_deadlines("Registration will open soon") == {}
