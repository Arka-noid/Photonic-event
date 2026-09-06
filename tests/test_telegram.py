from datetime import date

from collector.deadlines import due_reminders
from collector.digest import build_digest, build_reminders, fmt_period
from collector.models import Event
from collector.notify.telegram import LIMIT, esc, split_message
from collector.store import Diff


class FakeResult:
    def __init__(self, id, ok=True, n_events=1, skipped=""):
        self.id, self.ok, self.n_events, self.skipped = id, ok, n_events, skipped


def test_escape_html_evita_messaggi_rifiutati_da_telegram():
    assert esc("AI & <Photonics>") == "AI &amp; &lt;Photonics&gt;"


def test_i_messaggi_restano_sotto_il_limite_e_spezzano_sulle_righe():
    testo = "\n".join(f"riga {i} " + "x" * 100 for i in range(80))
    pezzi = split_message(testo)
    assert len(pezzi) > 1
    assert all(len(p) <= LIMIT for p in pezzi)
    assert all(not p.startswith("x") for p in pezzi)  # nessun taglio a metà riga


def test_una_riga_piu_lunga_del_limite_viene_comunque_spezzata():
    pezzi = split_message("y" * 9000)
    assert all(len(p) <= LIMIT for p in pezzi)
    assert "".join(pezzi) == "y" * 9000


def test_periodo_compatto_quando_stesso_mese():
    assert fmt_period(Event(title="X", start="2026-05-10", end="2026-05-14")) == "10–14 mag 2026"
    assert fmt_period(Event(title="X", start="2026-05-10")) == "10 mag 2026"
    assert fmt_period(Event(title="X")) == "date da definire"


def test_nessuna_novita_nessun_messaggio():
    assert build_digest(Diff(), [FakeResult("a")], date(2026, 1, 10)) is None


def test_il_digest_segnala_le_date_da_confermare_e_le_fonti_rotte():
    evento = Event(title="Photonic AI 2026", start="2026-05-10", confidence="unconfirmed", score=9)
    messaggio = build_digest(
        Diff(new=[evento]),
        [FakeResult("watchlist"), FakeResult("spie", ok=False, n_events=0), FakeResult("llm", skipped="no key")],
        date(2026, 1, 10),
    )
    assert "(da confermare)" in messaggio
    assert "spie" in messaggio and "non raggiungibili" in messaggio
    assert "llm" not in messaggio  # una fonte disattivata non è un guasto


def test_il_promemoria_riporta_i_giorni_reali_non_la_soglia():
    evento = Event(title="X 2026", deadlines={"paper": "2026-02-01"})
    messaggio = build_reminders(due_reminders([evento], date(2026, 1, 29)), date(2026, 1, 29))
    assert "fra 3 giorni" in messaggio


def test_nessun_promemoria_nessun_messaggio():
    assert build_reminders([], date(2026, 1, 10)) is None


def test_una_data_nota_solo_al_mese_non_viene_spacciata_per_un_giorno():
    approssimativo = Event(title="X", start="2026-10-01", date_precision="month")
    assert fmt_period(approssimativo) == "ottobre 2026"
    esatto = Event(title="X", start="2026-10-01")
    assert fmt_period(esatto) == "1 ott 2026"
