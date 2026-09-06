"""Scraper dichiarativo a selettori CSS.

I selettori vivono nel registry, non nel codice: quando un sito cambia layout si
corregge un file YAML, non un modulo Python. Sintassi dei campi:

    title: "h3"          -> testo del primo match
    link:  "a@href"      -> attributo href del primo match
    date:  ".when"       -> testo, poi passato al parser di date

Nessun selettore in questo repository è stato verificato contro il sito vero:
la rete dell'ambiente di sviluppo non raggiunge i siti delle società scientifiche.
Vanno tarati con `run.py probe` alla prima esecuzione su GitHub Actions.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..dateparse import extract_deadlines, parse_range
from .base import Fetcher, make_event, require_url


def _pick(node, selector: str | None, base_url: str = "") -> str:
    """Applica un selettore, con il suffisso '@attributo' opzionale."""
    if not selector:
        return ""
    attribute = None
    if "@" in selector:
        selector, attribute = selector.rsplit("@", 1)
    found = node.select_one(selector.strip()) if selector.strip() else node
    if found is None:
        return ""
    if attribute:
        value = found.get(attribute, "") or ""
        return urljoin(base_url, value) if attribute == "href" and base_url else value
    return " ".join(found.get_text(" ", strip=True).split())


def parse(body: bytes, entry: dict) -> list:
    selectors = entry.get("selectors") or {}
    item_selector = selectors.get("item")
    if not item_selector:
        raise ValueError("selectors.item mancante nel registry")

    soup = BeautifulSoup(body, "lxml")
    base_url = entry.get("url", "")
    events = []
    for node in soup.select(item_selector):
        title = _pick(node, selectors.get("title")) or _pick(node, "a")
        date_text = _pick(node, selectors.get("date"))
        blob = node.get_text(" ", strip=True)
        start, end = parse_range(date_text or blob)
        event = make_event(
            title=title,
            url=_pick(node, selectors.get("link", "a@href"), base_url),
            start=start,
            end=end,
            location=_pick(node, selectors.get("location")) or None,
            description=_pick(node, selectors.get("description")),
            deadlines=extract_deadlines(_pick(node, selectors.get("deadline")) or blob),
            source=entry["id"],
            topics=list(entry.get("topics_default") or []),
            kind=entry.get("kind_default"),
        )
        if event:
            events.append(event)
    return events


def handler(entry: dict, fetcher: Fetcher):
    # Il selettore si valida prima del fetch: è inutile scaricare una pagina che
    # non sapremmo comunque leggere, e l'errore così è quello davvero utile.
    if not (entry.get("selectors") or {}).get("item"):
        raise ValueError(f"selectors.item mancante nel registry per la fonte {entry.get('id', '?')!r}")
    fetched = fetcher.get(require_url(entry), entry.get("fixture"))
    if not fetched.ok:
        return [], fetched
    return parse(fetched.body, entry), fetched
