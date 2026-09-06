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
        diff, _ = collect(registry, store, Fetcher(offline=True), date(2026, 9, 6))
        assert [e.title for e in diff.new] == ["Photonics Next 2027"]
    finally:
        del pipeline.HANDLERS["fake"]
