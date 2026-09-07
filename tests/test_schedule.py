from datetime import date
from pathlib import Path

import pytest

from collector.schedule import (
    Schedule,
    ScheduleError,
    load_schedule,
    parse,
    save_schedule,
    site_payload,
    write_site_payload,
)
from collector.run import main

REPO = Path(__file__).resolve().parent.parent

# Settimana di riferimento: 7 settembre 2026 è un lunedì.
MONDAY = date(2026, 9, 7)
TUESDAY = date(2026, 9, 8)
THURSDAY = date(2026, 9, 10)
NEXT_MONDAY = date(2026, 9, 14)


def test_daily_aggiorna_sempre():
    schedule = Schedule(frequency="daily")
    assert all(schedule.should_run(date(2026, 9, day)) for day in range(7, 14))


def test_weekly_aggiorna_solo_nei_giorni_scelti():
    schedule = Schedule(frequency="weekly", days=(0, 3))
    assert schedule.should_run(MONDAY)
    assert schedule.should_run(THURSDAY)
    assert not schedule.should_run(TUESDAY)


def test_biweekly_salta_una_settimana_su_due():
    schedule = Schedule(frequency="biweekly", days=(0,))
    lunedi = [MONDAY, NEXT_MONDAY, date(2026, 9, 21), date(2026, 9, 28)]
    attivi = [day for day in lunedi if schedule.should_run(day)]
    assert len(attivi) == 2
    assert (attivi[1] - attivi[0]).days == 14


def test_biweekly_non_salta_un_turno_al_cambio_danno():
    # Con il numero di settimana ISO la parità si ripete fra la 53 e la 1: qui
    # il conteggio è sugli ordinali, quindi l'intervallo resta di 14 giorni.
    schedule = Schedule(frequency="biweekly", days=(0,))
    lunedi = [date(2026, 12, 21), date(2026, 12, 28), date(2027, 1, 4), date(2027, 1, 11)]
    attivi = [day for day in lunedi if schedule.should_run(day)]
    assert (attivi[1] - attivi[0]).days == 14


def test_monthly_scala_allultimo_giorno_nei_mesi_corti():
    schedule = Schedule(frequency="monthly", day_of_month=31)
    assert schedule.should_run(date(2026, 1, 31))
    assert schedule.should_run(date(2026, 2, 28))      # febbraio non viene saltato
    assert not schedule.should_run(date(2026, 2, 27))
    assert schedule.should_run(date(2028, 2, 29))      # bisestile


def test_next_runs_esclude_oggi_ed_e_stabile_fino_al_prossimo_giro():
    schedule = Schedule(frequency="weekly", days=(0, 3))
    assert schedule.next_runs(MONDAY, 3) == [THURSDAY, NEXT_MONDAY, date(2026, 9, 17)]
    # Ricalcolare nei giorni intermedi dà lo stesso risultato: il file per il
    # sito non cambia, quindi i workflow non committano per nulla.
    assert schedule.next_runs(TUESDAY, 3) == schedule.next_runs(MONDAY, 3)


def test_descrizioni_in_italiano():
    assert Schedule("daily").describe() == "ogni giorno"
    assert Schedule("weekly", (0, 3)).describe() == "ogni lunedì e giovedì"
    assert Schedule("biweekly", (4,)).describe() == "a settimane alterne, di venerdì"
    assert Schedule("monthly", day_of_month=15).describe() == "il 15 di ogni mese"


# -- lettura della configurazione ------------------------------------------------

def test_i_giorni_si_scrivono_in_italiano_o_in_inglese():
    assert parse({"frequency": "weekly", "days": ["lunedì", "THU"]}).days == (0, 3)
    assert parse({"frequency": "weekly", "days": "martedì, venerdì"}).days == (1, 4)
    assert parse({"frequency": "weekly", "days": [0, 6]}).days == (0, 6)


def test_una_configurazione_sbagliata_avvisa_e_torna_a_ogni_giorno():
    # Il caso peggiore sarebbe smettere di aggiornare in silenzio.
    schedule = parse({"frequency": "ogni tanto"})
    assert schedule.frequency == "daily"
    assert schedule.warnings

    giorni = parse({"frequency": "weekly", "days": ["lunedì", "pippo"]})
    assert giorni.days == (0, 3)          # i giorni predefiniti
    assert giorni.warnings

    mese = parse({"frequency": "monthly", "day_of_month": 99})
    assert mese.day_of_month == 1
    assert mese.warnings


def test_file_mancante_significa_ogni_giorno(tmp_path):
    schedule = load_schedule(tmp_path / "schedule.yaml")
    assert schedule.frequency == "daily"
    assert not schedule.warnings


def test_file_illeggibile_avvisa_senza_fermare_la_raccolta(tmp_path):
    path = tmp_path / "schedule.yaml"
    path.write_text("frequency: [non\n  chiuso", encoding="utf-8")
    schedule = load_schedule(path)
    assert schedule.frequency == "daily"
    assert schedule.warnings


def test_scrittura_e_rilettura_conservano_la_scelta(tmp_path):
    path = tmp_path / "schedule.yaml"
    save_schedule(path, Schedule("biweekly", (1, 4), 12))
    riletta = load_schedule(path)
    assert (riletta.frequency, riletta.days, riletta.day_of_month) == ("biweekly", (1, 4), 12)
    assert "# Ogni quanto" in path.read_text(encoding="utf-8")   # i commenti restano


# -- modifica da riga di comando -------------------------------------------------

def test_da_riga_di_comando_un_refuso_viene_rifiutato():
    # Al contrario del file del repository: qui c'è qualcuno che legge l'errore.
    with pytest.raises(ScheduleError):
        Schedule().updated(frequency="settimanale")
    with pytest.raises(ScheduleError):
        Schedule().updated(days="lunedì, pippo")
    with pytest.raises(ScheduleError):
        Schedule().updated(day_of_month=0)


def test_updated_cambia_solo_i_campi_indicati():
    schedule = Schedule("weekly", (0, 3), 5).updated(frequency="monthly")
    assert (schedule.frequency, schedule.days, schedule.day_of_month) == ("monthly", (0, 3), 5)


# -- copia per il sito -----------------------------------------------------------

def test_il_sito_riceve_descrizione_e_prossime_date():
    payload = site_payload(Schedule("weekly", (0, 3)), MONDAY)
    assert payload["description"] == "ogni lunedì e giovedì"
    assert payload["days"] == ["lunedì", "giovedì"]
    assert payload["next_runs"][0] == "2026-09-10"


def test_con_daily_non_si_scrivono_date_che_cambierebbero_ogni_giorno(tmp_path):
    path = tmp_path / "schedule.json"
    write_site_payload(path, Schedule("daily"), MONDAY)
    prima = path.read_text(encoding="utf-8")
    write_site_payload(path, Schedule("daily"), TUESDAY)
    assert path.read_text(encoding="utf-8") == prima


# -- integrazione con la CLI -----------------------------------------------------

def _cli(tmp_path, command, *args):
    # Le opzioni vanno dopo il sottocomando: è la forma che la CLI accetta
    # davvero (il sottoparser rimette i propri valori predefiniti).
    return main([command, "--root", str(REPO), "--data-dir", str(tmp_path), *args])


def test_il_comando_schedule_scrive_entrambi_i_file(tmp_path):
    assert _cli(tmp_path, "schedule", "--set", "weekly", "--days", "lunedì,giovedì",
                "--today", "2026-09-07") == 0
    assert "frequency: weekly" in (tmp_path / "schedule.yaml").read_text(encoding="utf-8")
    assert (tmp_path / "schedule.json").exists()


def test_il_comando_schedule_rifiuta_una_frequenza_inventata(tmp_path):
    with pytest.raises(SystemExit):          # argparse: scelta non ammessa
        _cli(tmp_path, "schedule", "--set", "quando-capita")


def test_la_raccolta_salta_i_giorni_non_previsti(tmp_path, capsys):
    save_schedule(tmp_path / "schedule.yaml", Schedule("weekly", (0, 3)))
    assert _cli(tmp_path, "collect", "--offline", "--dry-run", "--today", "2026-09-08") == 0
    assert "non è un giorno di aggiornamento" in capsys.readouterr().out
    assert not (tmp_path / "events.json").exists()      # nessuna fonte interrogata


def test_force_ignora_la_cadenza(tmp_path, capsys):
    save_schedule(tmp_path / "schedule.yaml", Schedule("weekly", (0, 3)))
    assert _cli(tmp_path, "collect", "--offline", "--dry-run", "--force", "--today", "2026-09-08") == 0
    assert "non è un giorno di aggiornamento" not in capsys.readouterr().out
    assert (tmp_path / "events.json").exists()
