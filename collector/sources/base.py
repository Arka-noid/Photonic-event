"""Infrastruttura comune alle fonti: fetch, esecuzione fail-soft, esito.

La regola che governa questo file: **nessuna fonte può far fallire la run**.
Un 403, un timeout, un HTML ristrutturato o un selettore sbagliato producono un
`SourceResult` con `ok=False` e un messaggio — che finisce in data/health.json,
in fondo al sito e in coda al digest Telegram. Il sistema è stato progettato
sapendo che gli scraper non si potevano provare contro i siti veri prima del
primo giro su GitHub Actions, quindi il silenzio non è un'opzione: se una fonte
smette di funzionare, deve dirlo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import requests

USER_AGENT = (
    "Photonic-event/1.0 (+https://github.com/Arka-noid/Photonic-event) "
    "raccolta eventi accademici; contatto via issue del repository"
)
TIMEOUT = 25
MAX_RETRIES = 2


class SkipSource(Exception):
    """La fonte non è applicabile in questa run (manca una chiave, siamo offline).

    Non è un fallimento: viene registrata come `skipped` e non sporca lo stato
    di salute con un falso allarme.
    """


@dataclass
class FetchResult:
    ok: bool
    status: int | None = None
    body: bytes = b""
    error: str = ""
    url: str = ""

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class SourceResult:
    """Esito di una fonte in una run. È esattamente ciò che finisce in health.json."""

    id: str
    name: str
    ok: bool = False
    http_status: int | None = None
    n_events: int = 0
    #: `error` = la fonte non ha funzionato. `warning` = ha funzionato ma c'è
    #: qualcosa da sapere (zero risultati, dataset vecchio). Sono cose diverse e
    #: sul sito vengono mostrate diversamente.
    error: str = ""
    warning: str = ""
    skipped: str = ""
    events: list = field(default_factory=list)
    raw: bytes = b""

    def to_health(self, today: date) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "ok": self.ok,
            "http_status": self.http_status,
            "n_events": self.n_events,
            "error": self.error[:300],
            "warning": self.warning[:300],
            "skipped": self.skipped,
            "checked_at": today.isoformat(),
        }


class Fetcher:
    """Client HTTP con un solo scopo, più la modalità offline per i test.

    In offline mode nessuna richiesta parte: si legge il file indicato da
    `fixture` nel registry. È ciò che rende `collect --offline` un test vero e
    non una finzione.
    """

    def __init__(self, offline: bool = False, base_dir: str | Path = ".") -> None:
        self.offline = offline
        self.base_dir = Path(base_dir)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en,it;q=0.8"})

    def get(self, url: str, fixture: str | None = None) -> FetchResult:
        if self.offline:
            if not fixture:
                return FetchResult(False, None, error="offline: nessuna fixture configurata", url=url)
            path = self.base_dir / fixture
            if not path.exists():
                return FetchResult(False, None, error=f"offline: fixture mancante {fixture}", url=url)
            return FetchResult(True, 200, path.read_bytes(), url=url)

        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=TIMEOUT)
                if response.status_code >= 500 and attempt < MAX_RETRIES:
                    last_error = f"HTTP {response.status_code}"
                    time.sleep(2 ** attempt)
                    continue
                ok = response.status_code < 400
                return FetchResult(
                    ok,
                    response.status_code,
                    response.content,
                    "" if ok else f"HTTP {response.status_code}",
                    url,
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** attempt)
        return FetchResult(False, None, error=last_error, url=url)


def require_url(entry: dict) -> str:
    """Legge `url` dal registry con un errore comprensibile se manca.

    Senza questo una voce mal scritta fallisce con un opaco KeyError: 'url' in
    health.json, che non dice a chi legge cosa sistemare.
    """
    url = entry.get("url")
    if not url:
        raise ValueError(f"campo 'url' mancante nel registry per la fonte {entry.get('id', '?')!r}")
    return url


def run_source(
    entry: dict,
    handler: Callable[[dict, Fetcher], tuple[list, FetchResult | None]],
    fetcher: Fetcher,
) -> SourceResult:
    """Esegue una fonte assorbendone qualunque fallimento."""
    result = SourceResult(id=entry.get("id", "?"), name=entry.get("name", entry.get("id", "?")))
    try:
        events, fetched = handler(entry, fetcher)
    except SkipSource as exc:
        result.skipped = str(exc)
        result.ok = True
        return result
    except Exception as exc:  # volutamente ampio: una fonte rotta non ferma le altre
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    if fetched is not None:
        result.http_status = fetched.status
        result.raw = fetched.body
        if not fetched.ok:
            result.error = fetched.error or "fetch fallito"
            return result

    result.events = events
    result.n_events = len(events)
    result.ok = True
    if entry.get("_warning"):
        result.warning = entry.pop("_warning")
    if not events:
        # Non è un errore, ma quasi sempre è il sintomo di un selettore da rivedere.
        result.warning = "; ".join(filter(None, [result.warning, "nessun evento estratto (selettore da verificare?)"]))
    return result


def make_event(
    title: str,
    url: str = "",
    listing_url: str = "",
    start=None,
    end=None,
    location: str | None = None,
    description: str = "",
    deadlines: dict | None = None,
    source: str = "",
    kind: str | None = None,
    topics: list | None = None,
    confidence: str = "confirmed",
    date_precision: str = "day",
    min_score: int = 1,
):
    """Costruisce un Event applicando pertinenza, regione e tipo.

    Ritorna None se l'evento non è pertinente: il filtro sta qui, in un punto solo,
    così tutte le fonti si comportano allo stesso modo.
    """
    from ..models import Event
    from ..relevance import detect_kind, detect_region, score_event

    title = " ".join((title or "").split())
    if not title:
        return None

    scored = score_event(title, description, location)
    if not scored["relevant"] or scored["score"] < min_score:
        return None

    return Event(
        title=title,
        url=url or "",
        listing_url=listing_url or "",
        kind=kind or detect_kind(title, description),
        topics=sorted(set((topics or []) + scored["topics"])),
        start=start,
        end=end,
        location=location,
        region=detect_region(location, title, description),
        deadlines=deadlines or {},
        source=source,
        confidence=confidence,
        date_precision=date_precision,
        description=" ".join((description or "").split())[:500],
        score=scored["score"],
    )
