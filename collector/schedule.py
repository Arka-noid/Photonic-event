"""Frequenza di aggiornamento: in quali giorni il sito viene ricostruito.

Il cron di GitHub Actions è scritto dentro il workflow e non accetta variabili:
non è cambiabile da fuori. Quindi il workflow parte **ogni mattina** e la
decisione di aggiornare o no la prende questo modulo, leggendo
`data/schedule.yaml`. Cambiare cadenza è una riga di configurazione (o un
comando), non una modifica al workflow.

Due modi di leggere la configurazione, volutamente diversi:

* `parse` è indulgente — un valore sbagliato nel file del repository produce un
  avviso e si torna a `daily`. Meglio aggiornare più del previsto che smettere
  in silenzio: sarebbe l'unico guasto di cui nessuno si accorgerebbe.
* `Schedule.updated` è severa — un refuso scritto a riga di comando viene
  rifiutato subito, quando l'utente è ancora lì a leggerlo.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from .models import iso, strip_accents

#: Cadenze riconosciute.
FREQUENCIES = ("daily", "weekly", "biweekly", "monthly")

DEFAULT_FREQUENCY = "daily"
#: Giorni usati da `weekly`/`biweekly` quando la configurazione non li indica.
DEFAULT_DAYS = (0, 3)                      # lunedì e giovedì
DEFAULT_DAY_OF_MONTH = 1

WEEKDAY_LABELS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")

#: Nomi accettati in configurazione: italiano e inglese, per esteso o abbreviati.
#: Le chiavi sono senza accenti e minuscole, come le riduce `_weekday`.
WEEKDAY_NAMES = {
    "lunedi": 0, "lun": 0, "monday": 0, "mon": 0,
    "martedi": 1, "mar": 1, "tuesday": 1, "tue": 1,
    "mercoledi": 2, "mer": 2, "wednesday": 2, "wed": 2,
    "giovedi": 3, "gio": 3, "thursday": 3, "thu": 3,
    "venerdi": 4, "ven": 4, "friday": 4, "fri": 4,
    "sabato": 5, "sab": 5, "saturday": 5, "sat": 5,
    "domenica": 6, "dom": 6, "sunday": 6, "sun": 6,
}

#: Quanto lontano cercare le prossime date di aggiornamento (giorni).
_HORIZON_DAYS = 800


class ScheduleError(ValueError):
    """Configurazione rifiutata: usata solo sulla via severa (riga di comando)."""


def _weekday(value) -> int:
    """Nome o numero di giorno → 0-6, con 0 = lunedì. Alza `ScheduleError`."""
    if isinstance(value, bool):              # in YAML `days: [yes]` diventa True
        raise ScheduleError(f"giorno non valido: {value!r}")
    if isinstance(value, int):
        if 0 <= value <= 6:
            return value
        raise ScheduleError(f"giorno fuori intervallo: {value} (0 = lunedì, 6 = domenica)")
    name = strip_accents(str(value)).strip().lower()
    if name in WEEKDAY_NAMES:
        return WEEKDAY_NAMES[name]
    raise ScheduleError(f"giorno sconosciuto: {value!r}")


def parse_days(value) -> tuple[int, ...]:
    """Legge una lista di giorni. Accetta anche 'lunedì, giovedì' come stringa."""
    if value is None:
        return ()
    items = value.replace(",", " ").split() if isinstance(value, str) else value
    if isinstance(items, (int, bool)):       # `days: 3`, senza parentesi quadre
        items = [items]
    try:
        parsed = {_weekday(item) for item in items}
    except TypeError as error:               # non iterabile: dizionario, ecc.
        raise ScheduleError(f"lista di giorni non valida: {value!r}") from error
    return tuple(sorted(parsed))


def _day_in_month(day_of_month: int, when: date) -> int:
    """Il giorno del mese, ridotto all'ultimo disponibile nei mesi più corti.

    Chi chiede 'il 31' non intende 'mai a febbraio'."""
    return min(day_of_month, calendar.monthrange(when.year, when.month)[1])


def _week_index(when: date) -> int:
    """Numero della settimana contato dall'inizio del calendario proleptico.

    Non si usa il numero ISO: fra la settimana 53 e la 1 la parità si ripete e
    `biweekly` salterebbe un turno al cambio d'anno. Questo conteggio è monotono
    per costruzione (l'ordinale 1 cade di lunedì)."""
    return (when.toordinal() - 1) // 7


def _join(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} e {labels[-1]}"


@dataclass
class Schedule:
    """Ogni quanto, e in che giorni, rifare la raccolta e quindi il sito."""

    frequency: str = DEFAULT_FREQUENCY
    days: tuple[int, ...] = DEFAULT_DAYS
    day_of_month: int = DEFAULT_DAY_OF_MONTH
    #: Problemi trovati nella configurazione: mai fatali, ma vanno detti.
    warnings: list[str] = field(default_factory=list)

    # -- decisioni -----------------------------------------------------------

    def should_run(self, today: date) -> bool:
        if self.frequency == "weekly":
            return today.weekday() in self.days
        if self.frequency == "biweekly":
            return today.weekday() in self.days and _week_index(today) % 2 == 0
        if self.frequency == "monthly":
            return today.day == _day_in_month(self.day_of_month, today)
        return True                          # 'daily', e qualsiasi cosa non riconosciuta

    def next_runs(self, today: date, count: int = 3) -> list[date]:
        """Le prossime date di aggiornamento, **dopo** oggi.

        Escludere oggi rende il valore stabile fino al prossimo aggiornamento:
        rigenerarlo ogni mattina non produce un file diverso, quindi il sito non
        viene ripubblicato per nulla."""
        found: list[date] = []
        cursor = today
        for _ in range(_HORIZON_DAYS):
            cursor += timedelta(days=1)
            if self.should_run(cursor):
                found.append(cursor)
                if len(found) == count:
                    break
        return found

    # -- descrizione ---------------------------------------------------------

    def describe(self) -> str:
        """Una riga in italiano, mostrata dalla CLI e in fondo al sito."""
        labels = [WEEKDAY_LABELS[d] for d in self.days]
        if self.frequency == "weekly":
            return f"ogni {_join(labels)}"
        if self.frequency == "biweekly":
            return f"a settimane alterne, di {_join(labels)}"
        if self.frequency == "monthly":
            tail = " (o l'ultimo giorno, nei mesi più corti)" if self.day_of_month > 28 else ""
            return f"il {self.day_of_month} di ogni mese{tail}"
        return "ogni giorno"

    # -- modifica ------------------------------------------------------------

    def updated(self, frequency=None, days=None, day_of_month=None) -> "Schedule":
        """Copia con i campi indicati sostituiti. Via severa: alza `ScheduleError`.

        Serve alla riga di comando, dove un refuso va detto in faccia invece di
        essere corretto di nascosto."""
        new = Schedule(self.frequency, self.days, self.day_of_month)

        if frequency is not None:
            wanted = str(frequency).strip().lower()
            if wanted not in FREQUENCIES:
                raise ScheduleError(
                    f"frequenza sconosciuta: {frequency!r} (scegli fra {', '.join(FREQUENCIES)})")
            new.frequency = wanted
        if days is not None:
            parsed = parse_days(days)
            if not parsed:
                raise ScheduleError("serve almeno un giorno della settimana")
            new.days = parsed
        if day_of_month is not None:
            number = int(day_of_month)
            if not 1 <= number <= 31:
                raise ScheduleError(f"giorno del mese fuori intervallo: {number} (1-31)")
            new.day_of_month = number

        if new.frequency in ("weekly", "biweekly") and not new.days:
            raise ScheduleError(f"la frequenza '{new.frequency}' richiede almeno un giorno")
        return new

    # -- serializzazione -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "frequency": self.frequency,
            "days": [WEEKDAY_LABELS[d] for d in self.days],
            "day_of_month": self.day_of_month,
        }


def parse(raw: dict | None) -> Schedule:
    """Legge la configurazione. Via indulgente: corregge e segnala, non fallisce."""
    schedule = Schedule()
    if raw is None:
        return schedule
    if not isinstance(raw, dict):
        schedule.warnings.append(f"configurazione non valida ({type(raw).__name__}): uso 'ogni giorno'")
        return schedule

    frequency = str(raw.get("frequency", DEFAULT_FREQUENCY)).strip().lower()
    if frequency not in FREQUENCIES:
        schedule.warnings.append(
            f"frequenza sconosciuta: {raw.get('frequency')!r} (fra {', '.join(FREQUENCIES)}): uso 'ogni giorno'")
        frequency = DEFAULT_FREQUENCY

    days = DEFAULT_DAYS
    if "days" in raw:
        try:
            days = parse_days(raw["days"]) or DEFAULT_DAYS
        except ScheduleError as error:
            schedule.warnings.append(f"{error}: uso {_join([WEEKDAY_LABELS[d] for d in DEFAULT_DAYS])}")

    day_of_month = DEFAULT_DAY_OF_MONTH
    if "day_of_month" in raw:
        try:
            day_of_month = int(raw["day_of_month"])
        except (TypeError, ValueError):
            schedule.warnings.append(f"giorno del mese non numerico: {raw['day_of_month']!r}: uso il {day_of_month}")
        else:
            if not 1 <= day_of_month <= 31:
                schedule.warnings.append(f"giorno del mese fuori intervallo: {day_of_month}: uso il 1")
                day_of_month = DEFAULT_DAY_OF_MONTH

    schedule.frequency = frequency
    schedule.days = days
    schedule.day_of_month = day_of_month
    return schedule


def load_schedule(path: str | Path) -> Schedule:
    """Carica `data/schedule.yaml`. Il file è opzionale: senza, si aggiorna ogni giorno."""
    path = Path(path)
    if not path.exists():
        return Schedule()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        schedule = Schedule()
        schedule.warnings.append(f"{path.name} illeggibile ({error}): uso 'ogni giorno'")
        return schedule
    return parse(raw)


#: Il file si scrive da un modello invece che con `yaml.dump`: i commenti sono
#: metà del suo valore e un dump li cancellerebbe a ogni modifica dalla CLI.
_TEMPLATE = """\
# Ogni quanto aggiornare il sito, e in che giorni.
#
#   frequency: daily      ogni giorno
#              weekly     nei giorni elencati in 'days'
#              biweekly   negli stessi giorni, ma a settimane alterne
#              monthly    una volta al mese, il giorno 'day_of_month'
#
#   days:         giorni della settimana per weekly/biweekly, in italiano o in
#                 inglese ([lunedì, giovedì], [mon, thu], …)
#   day_of_month: giorno del mese per monthly; nei mesi più corti scala
#                 all'ultimo giorno disponibile
#
# Il workflow parte comunque ogni mattina: se oggi non è un giorno di
# aggiornamento esce subito, senza interrogare nessuna fonte. I promemoria delle
# scadenze restano giornalieri: dipendono dal calendario delle conferenze, non
# da questa cadenza.
#
# Si può modificare a mano oppure con:
#   python -m collector.run schedule --set weekly --days lunedì,giovedì
frequency: {frequency}
days: [{days}]
day_of_month: {day_of_month}
"""


def save_schedule(path: str | Path, schedule: Schedule) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _TEMPLATE.format(
            frequency=schedule.frequency,
            days=", ".join(WEEKDAY_LABELS[d] for d in schedule.days),
            day_of_month=schedule.day_of_month,
        ),
        encoding="utf-8",
    )


def site_payload(schedule: Schedule, today: date) -> dict:
    # Con 'daily' le prossime date si spostano ogni mattina e il file cambierebbe
    # tutti i giorni, facendo committare i workflow anche quando non c'è nessuna
    # novità. È anche l'unico caso in cui la data non aggiunge niente: il
    # prossimo aggiornamento è domani, sempre.
    next_runs = [] if schedule.frequency == "daily" else [iso(d) for d in schedule.next_runs(today)]
    return {
        **schedule.to_dict(),
        "description": schedule.describe(),
        "next_runs": next_runs,
        "warnings": list(schedule.warnings),
    }


def write_site_payload(path: str | Path, schedule: Schedule, today: date) -> None:
    """Scrive `data/schedule.json`, la copia che legge il sito.

    Il sito è statico e non sa leggere YAML; questo file è la traduzione. Viene
    riscritto a ogni invocazione della raccolta, anche in quelle che saltano,
    così una modifica alla cadenza compare online il giorno dopo invece di
    aspettare il prossimo aggiornamento vero."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(site_payload(schedule, today), indent=2, ensure_ascii=False) + "\n"
    # Riscrivere lo stesso contenuto sporcherebbe il diff e farebbe ripubblicare
    # il sito per nulla: i workflow committano tutto ciò che risulta cambiato.
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return
    path.write_text(payload, encoding="utf-8")
