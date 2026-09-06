"""Scoperta di eventi tramite ricerca web di Claude — fonte OPZIONALE.

Si auto-disattiva se manca `ANTHROPIC_API_KEY`: in quel caso la run continua
normalmente e health.json riporta `skipped`. Aggiungere la chiave ai secrets del
repository è l'unica cosa necessaria per accenderla, senza toccare il codice.

Costo: la ricerca web è la parte cara della pipeline. `max_queries` nel registry
tiene il conto delle richieste per run.
"""

from __future__ import annotations

import json
import os
from datetime import date

from .base import Fetcher, SkipSource, make_event

MODEL = "claude-opus-5"

EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "start": {"type": "string", "description": "AAAA-MM-GG, vuoto se ignota"},
                    "end": {"type": "string"},
                    "location": {"type": "string"},
                    "kind": {"type": "string", "enum": ["conference", "school", "workshop", "special-session", "other"]},
                    "abstract_deadline": {"type": "string"},
                    "paper_deadline": {"type": "string"},
                    "registration_deadline": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "url"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["events"],
    "additionalProperties": False,
}

DEFAULT_QUERIES = [
    "conferenze e call for papers {year} su neuromorphic photonics e photonic neural networks",
    "summer school e winter school {year} su fotonica integrata e machine learning",
    "workshop {year} su optical computing, reservoir computing e AI accelerator fotonici",
]

SYSTEM = (
    "Sei un assistente che cataloga eventi accademici su fotonica e reti neurali. "
    "Riporta solo eventi reali di cui hai trovato conferma nei risultati di ricerca, "
    "con l'URL della pagina ufficiale. Non inventare date: se una data non compare "
    "nelle fonti, lascia il campo vuoto. Preferisci eventi futuri."
)


def _parse_payload(payload: dict, entry: dict) -> list:
    events = []
    for item in payload.get("events", []):
        deadlines = {
            "abstract": item.get("abstract_deadline") or None,
            "paper": item.get("paper_deadline") or None,
            "registration": item.get("registration_deadline") or None,
        }
        event = make_event(
            title=item.get("title", ""),
            url=item.get("url", ""),
            start=item.get("start") or None,
            end=item.get("end") or None,
            location=item.get("location") or None,
            description=item.get("description", ""),
            deadlines={k: v for k, v in deadlines.items() if v},
            source=entry["id"],
            kind=item.get("kind"),
            topics=list(entry.get("topics_default") or []),
            # Un LLM può sbagliare una data anche citando la fonte giusta:
            # queste voci restano da verificare finché non le conferma un'altra fonte.
            confidence="unconfirmed",
        )
        if event:
            events.append(event)
    return events


def handler(entry: dict, fetcher: Fetcher):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SkipSource("ANTHROPIC_API_KEY non impostata: fonte LLM disattivata")
    if fetcher.offline:
        raise SkipSource("modalità offline: fonte LLM disattivata")

    try:
        import anthropic
    except ImportError as exc:
        raise SkipSource(f"pacchetto 'anthropic' non installato ({exc})") from exc

    client = anthropic.Anthropic()
    year = date.today().year
    queries = entry.get("queries") or DEFAULT_QUERIES
    max_queries = int(entry.get("max_queries", 3))
    collected: list = []

    for query in queries[:max_queries]:
        response = client.messages.create(
            model=entry.get("model", MODEL),
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            tools=[{
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": int(entry.get("max_searches_per_query", 4)),
            }],
            output_config={"format": {"type": "json_schema", "schema": EVENT_SCHEMA}},
            messages=[{"role": "user", "content": query.format(year=year, next_year=year + 1)}],
        )
        # Gli errori dei server tool arrivano con HTTP 200: il blocco di risultato
        # contiene un oggetto errore al posto della lista. Va guardato prima di usarlo.
        for block in response.content:
            if getattr(block, "type", "") == "web_search_tool_result":
                content = getattr(block, "content", None)
                if isinstance(content, dict) or hasattr(content, "error_code"):
                    raise RuntimeError(f"web_search fallita: {content}")

        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        if text.strip():
            collected.extend(_parse_payload(json.loads(text), entry))

    return collected, None
