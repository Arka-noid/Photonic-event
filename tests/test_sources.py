from datetime import date

from conftest import FIXTURES

from collector.sources import aideadlines, html, ics, rss
from collector.sources.base import Fetcher, SkipSource, SourceResult, run_source


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# -- parser ------------------------------------------------------------------

def test_ics_scarta_il_fuori_tema_e_corregge_dtend_esclusivo():
    events = ics.parse(_read("sample.ics"), {"id": "test-ics", "topics_default": ["photonics"]})
    titoli = [e.title for e in events]
    assert "International Workshop on Photonic Neural Networks" in titoli
    assert "Annual Gathering of Cheese Makers" not in titoli

    pnn = next(e for e in events if e.title.startswith("International Workshop"))
    # DTEND=20260619 è esclusivo: l'ultimo giorno reale è il 18
    assert (pnn.start, pnn.end) == (date(2026, 6, 15), date(2026, 6, 18))
    assert pnn.deadlines == {"abstract": date(2026, 2, 15)}
    assert pnn.region == "europe"


def test_ics_riconosce_le_school():
    events = ics.parse(_read("sample.ics"), {"id": "t", "topics_default": []})
    school = next(e for e in events if "Summer School" in e.title)
    assert school.kind == "school"


def test_rss_legge_le_date_dal_testo_non_dalla_pubblicazione():
    events = rss.parse(_read("sample_rss.xml"), {"id": "test-rss", "topics_default": []})
    assert len(events) == 1                                   # il convegno di panetteria è scartato
    evento = events[0]
    assert (evento.start, evento.end) == (date(2026, 5, 10), date(2026, 5, 14))
    assert evento.deadlines == {"abstract": date(2025, 12, 1)}
    assert evento.region == "europe"


def test_html_risolve_i_link_relativi_e_filtra():
    entry = {
        "id": "test-html",
        "url": "https://example.test/events/",
        "topics_default": ["photonics"],
        "selectors": {"item": "article.event", "title": "h3", "link": "a@href",
                      "date": ".event-date", "location": ".event-location", "description": ".desc"},
    }
    events = html.parse(_read("sample_events.html"), entry)
    assert len(events) == 1                                   # rifiuti urbani scartati
    evento = events[0]
    assert evento.url == "https://example.test/events/ipdl-2026"
    assert (evento.start, evento.end) == (date(2026, 4, 12), date(2026, 4, 16))
    assert evento.deadlines == {"paper": date(2026, 1, 20)}


def test_html_senza_selettore_item_fallisce_in_modo_esplicito():
    result = run_source({"id": "x", "name": "X", "selectors": {}}, html.handler, Fetcher(offline=True))
    assert not result.ok and "selectors.item" in result.error


def test_aideadlines_scarta_le_edizioni_vecchie_e_avvisa_se_il_dataset_e_fermo():
    entry = {"id": "aid", "topics_default": ["ml"]}
    events, warning = aideadlines.parse(_read("sample_aideadlines.yml"), entry, today=date(2026, 9, 6))
    assert [e.title for e in events] == ["NEURIPS 2026"]
    assert events[0].deadlines == {"paper": date(2026, 5, 15), "abstract": date(2026, 5, 8)}
    assert warning == ""

    # dataset che non arriva all'anno in corso: deve dirlo
    _, warning = aideadlines.parse(_read("sample_aideadlines.yml"), entry, today=date(2030, 1, 1))
    assert "fermo al 2026" in warning


# -- runner fail-soft --------------------------------------------------------

def test_una_fonte_che_esplode_non_ferma_la_run():
    def boom(entry, fetcher):
        raise ValueError("selettore rotto")

    result = run_source({"id": "boom", "name": "Boom"}, boom, Fetcher(offline=True))
    assert not result.ok and "selettore rotto" in result.error and result.events == []


def test_una_fonte_disattivata_e_skipped_non_un_errore():
    def skip(entry, fetcher):
        raise SkipSource("nessuna chiave API")

    result = run_source({"id": "llm", "name": "LLM"}, skip, Fetcher(offline=True))
    assert result.ok and result.skipped and not result.error


def test_zero_risultati_e_un_avviso_non_un_errore():
    result = run_source({"id": "v", "name": "V"}, lambda e, f: ([], None), Fetcher(offline=True))
    assert result.ok and not result.error and "nessun evento" in result.warning


def test_fetch_offline_senza_fixture_non_solleva():
    fetched = Fetcher(offline=True).get("https://example.test", fixture=None)
    assert not fetched.ok and "offline" in fetched.error


def test_health_json_riporta_errore_e_avviso_separatamente():
    result = SourceResult(id="x", name="X", ok=True, n_events=0, warning="attenzione")
    health = result.to_health(date(2026, 1, 1))
    assert health["ok"] and health["warning"] == "attenzione" and health["error"] == ""


def test_eventi_gia_conclusi_non_entrano_come_novita(tmp_path):
    # Altrimenti il digest annuncerebbe come "nuovo" qualcosa che prune_past
    # rimuove nella stessa run.
    import yaml

    from collector.models import Event
    from collector.pipeline import collect
    from collector.store import Store

    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump([{"id": "x", "name": "X", "type": "fake"}]))

    import collector.pipeline as pipeline

    pipeline.HANDLERS["fake"] = lambda entry, fetcher: (
        [Event(title="Photonics Old 2026", start="2026-01-10", end="2026-01-12", source="x"),
         Event(title="Photonics Next 2027", start="2027-01-10", source="x")],
        None,
    )
    try:
        store = Store(tmp_path / "events.json")
        diff, _, _ = collect(registry, store, Fetcher(offline=True), date(2026, 9, 6))
        assert [e.title for e in diff.new] == ["Photonics Next 2027"]
    finally:
        del pipeline.HANDLERS["fake"]


# -- guardie sull'arricchimento della watchlist ------------------------------
# Entrambi questi casi si sono verificati davvero nella prima raccolta reale.

def test_le_date_di_un_altro_evento_sulla_stessa_pagina_non_confermano():
    from collector.sources.watchlist import _enrich

    # La pagina di SPIE Photonics Europe (aprile) pubblicizza Photonics West
    # (gennaio) nell'intestazione. Col solo controllo sull'anno, l'evento di
    # aprile risultava tenuto a fine gennaio e per giunta "confermato".
    pagina = "SPIE Photonics West 2027, 30 January - 4 February 2027."
    assert _enrich(pagina, 2027, 4)[:2] == (None, None)      # atteso aprile → rifiutato
    assert _enrich(pagina, 2027, 1)[:2] == (date(2027, 1, 30), date(2027, 2, 4))


def test_uno_slittamento_di_poche_settimane_resta_accettato():
    from collector.sources.watchlist import _enrich

    # Una conferenza può spostarsi di qualche settimana: la tolleranza non deve
    # essere così stretta da rifiutare l'edizione giusta.
    pagina = "The conference takes place 2 - 6 May 2027 in Munich."
    assert _enrich(pagina, 2027, 6)[0] == date(2027, 5, 2)


def test_scadenze_di_unaltra_edizione_vengono_scartate():
    from collector.sources.watchlist import _plausible_deadlines

    # icml.cc mostrava le scadenze del 2026 mentre annunciava il 2027: senza
    # filtro, l'iscrizione a ICML 2027 risultava chiusa 13 mesi prima.
    inizio = date(2027, 7, 1)
    assert _plausible_deadlines({"registration": date(2026, 5, 24)}, inizio) == {}
    assert _plausible_deadlines({"abstract": date(2027, 4, 1)}, inizio) == {"abstract": date(2027, 4, 1)}
    # né una scadenza successiva all'evento
    assert _plausible_deadlines({"paper": date(2027, 9, 1)}, inizio) == {}


def test_mesi_trattati_come_circolari():
    from collector.sources.watchlist import _months_apart

    assert _months_apart(12, 1) == 1      # dicembre e gennaio distano un mese
    assert _months_apart(1, 4) == 3
    assert _months_apart(6, 6) == 0


def test_le_scadenze_si_filtrano_anche_quando_la_data_in_pagina_e_rifiutata():
    """Regressione: ICML conservava l'iscrizione del 2026 perché il filtro sulle
    scadenze riceveva la data trovata in pagina, che era stata scartata, quindi
    None — e con None lasciava passare tutto. Va confrontata la data *attesa*."""
    import yaml

    from collector.sources.watchlist import build

    items = [{"name": "ICML", "url": "https://icml.test/", "typical_month": 7,
              "topics": ["ml"], "fixture": "tests/fixtures/icml_page.html"}]
    fetcher = Fetcher(offline=True, base_dir=".")
    events = build(items, {"id": "watchlist", "enrich": True}, fetcher, today=date(2026, 9, 6))

    assert len(events) == 1
    evento = events[0]
    assert evento.start == date(2027, 7, 1) and evento.confidence == "unconfirmed"
    assert evento.deadlines == {}, "la scadenza dell'edizione precedente va scartata"


# -- formato degli aggregatori ----------------------------------------------

def test_luogo_estratto_dalle_parentesi_quadre():
    from collector.sources.rss import extract_location

    assert extract_location("Conf [Qingdao, China] [Aug 7, 2026 - Aug 9, 2026]") == "Qingdao, China"
    assert extract_location("Workshop @ ECML [Naples] [Sep 7, 2026 - Sep 7, 2026]") == "Naples"
    # il gruppo con il mese è la data, non il luogo
    assert extract_location("Conf [Aug 7, 2026 - Aug 9, 2026]") is None
    assert extract_location("Senza parentesi") is None


def test_rss_di_un_aggregatore_conserva_la_scheda_e_la_data_di_fine():
    entry = {"id": "wikicfp-test", "topics_default": ["ml"], "is_listing": True}
    events = rss.parse(_read("sample_wikicfp.xml"), entry)

    assert len(events) == 1
    evento = events[0]
    assert (evento.start, evento.end) == (date(2026, 8, 7), date(2026, 8, 9))
    assert evento.location == "Qingdao, China"
    assert evento.region == "asia"
    assert evento.listing_url == "http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=1"
    assert not evento.link_resolved


# -- risoluzione del link ufficiale ------------------------------------------

def test_link_ufficiale_letto_accanto_alletichetta():
    from collector.links import resolve_official_url

    pagina = b"""<html><body><table>
      <tr><td>When</td><td>Aug 7, 2026</td></tr>
      <tr><td>Link:</td><td><a href="http://www.icaann.org/">http://www.icaann.org/</a></td></tr>
    </table><a href="https://twitter.com/wikicfp">twitter</a></body></html>"""
    assert resolve_official_url(pagina, "http://www.wikicfp.com/x") == "http://www.icaann.org/"


def test_senza_etichetta_si_ripiega_sul_primo_esterno():
    from collector.links import resolve_official_url

    pagina = b'<html><body><a href="https://conf2026.example.org/">sito</a></body></html>'
    assert resolve_official_url(pagina, "http://www.wikicfp.com/x") == "https://conf2026.example.org/"


def test_se_non_ce_nulla_di_utile_non_si_inventa_un_url():
    from collector.links import resolve_official_url

    pagina = b'<html><body><a href="http://www.wikicfp.com/y">y</a><a href="mailto:a@b.c">m</a></body></html>'
    assert resolve_official_url(pagina, "http://www.wikicfp.com/x") is None


def test_la_risoluzione_si_tenta_una_volta_sola_per_evento(tmp_path):
    from collector.models import Event
    from collector.pipeline import resolve_links
    from collector.sources.base import FetchResult
    from collector.store import Store

    pagina = b'<html><body><table><tr><td>Link:</td><td><a href="http://vero.example/">v</a></td></tr></table></body></html>'

    class FintoFetcher:
        offline = False

        def __init__(self):
            self.richieste = []

        def get(self, url, fixture=None):
            self.richieste.append(url)
            if "rotta" in url:
                return FetchResult(False, 404, error="HTTP 404")
            return FetchResult(True, 200, pagina)

    store = Store(tmp_path / "events.json")
    store.upsert_all([
        Event(title="Con scheda 2026", url="http://wikicfp.test/a", listing_url="http://wikicfp.test/a"),
        Event(title="Scheda rotta 2026", url="http://wikicfp.test/rotta", listing_url="http://wikicfp.test/rotta"),
        Event(title="CLEO 2027", url="https://cleoconference.org/"),
    ], date(2026, 9, 6))

    fetcher = FintoFetcher()
    assert resolve_links(store, fetcher) == (1, 2)

    per_titolo = {e.title: e for e in store.events.values()}
    assert per_titolo["Con scheda 2026"].url == "http://vero.example/"
    # la scheda irraggiungibile resta puntata a sé stessa, non a un URL inventato
    assert per_titolo["Scheda rotta 2026"].url == "http://wikicfp.test/rotta"
    # un evento senza scheda non viene nemmeno toccato
    assert per_titolo["CLEO 2027"].link_resolved is False

    # secondo giro: nessuna richiesta ripetuta, nemmeno per quella fallita
    secondo = FintoFetcher()
    assert resolve_links(store, secondo) == (0, 0)
    assert secondo.richieste == []


def test_il_link_risolto_sopravvive_alla_raccolta_successiva(tmp_path):
    from collector.models import Event
    from collector.store import Store

    store = Store(tmp_path / "events.json")
    store.upsert_all([Event(title="Conf 2026", url="http://wikicfp.test/a",
                            listing_url="http://wikicfp.test/a")], date(2026, 9, 6))
    evento = next(iter(store.events.values()))
    evento.url, evento.link_resolved = "http://vero.example/", True

    # la fonte ripropone il link grezzo della scheda a ogni giro
    store.upsert_all([Event(title="Conf 2026", url="http://wikicfp.test/a",
                            listing_url="http://wikicfp.test/a")], date(2026, 9, 9))
    assert evento.url == "http://vero.example/"
    assert evento.link_resolved is True
