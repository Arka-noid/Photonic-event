"""Risoluzione del link ufficiale di una conferenza a partire dalla sua scheda.

I feed RSS degli aggregatori (WikiCFP in primis) puntano alla propria pagina di
elenco, non al sito della conferenza. Il sito ufficiale è dentro quella pagina,
di solito accanto a un'etichetta "Link:".

La struttura HTML di quelle pagine **non era verificabile** in fase di scrittura
(il dominio non è raggiungibile dall'ambiente di sviluppo), quindi qui non c'è un
selettore singolo ma una catena di ripieghi decrescenti, e l'ultimo ripiego è
"non ho trovato nulla" — mai un URL inventato.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

#: Domini che non sono mai il sito di una conferenza.
NOISE_DOMAINS = (
    "wikicfp.com", "w3.org", "google.com", "googletagmanager.com", "gstatic.com",
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "youtube.com", "doi.org", "creativecommons.org", "adobe.com", "apple.com",
    "microsoft.com", "amazon.com", "paypal.com", "addthis.com", "sharethis.com",
    "researchgate.net", "mendeley.com", "wikipedia.org", "archive.org",
)

#: Etichette con cui una scheda annuncia il sito ufficiale.
LINK_LABELS = re.compile(r"\b(link|website|web\s*site|homepage|home\s*page|url|conference\s+site)\b\s*:?", re.I)

#: Quanto lontano dall'etichetta accettare un collegamento, in caratteri di testo.
LABEL_WINDOW = 120


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def is_external(url: str, listing_url: str = "") -> bool:
    """Un candidato plausibile: http(s), non un dominio di servizio, non la scheda stessa."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    host = _host(url)
    if not host or "." not in host:
        return False
    if any(host == d or host.endswith("." + d) for d in NOISE_DOMAINS):
        return False
    return host != _host(listing_url)


def resolve_official_url(html: bytes | str, listing_url: str = "") -> str | None:
    """Il sito ufficiale trovato nella scheda, o None se non se ne riconosce uno.

    Tre livelli, dal più affidabile al più permissivo:

    1. il primo collegamento esterno che segue da vicino un'etichetta "Link:"
    2. altrimenti il primo collegamento esterno della pagina
    3. altrimenti None — si tiene la scheda, senza fingere di avere un indirizzo
    """
    soup = BeautifulSoup(html, "lxml")
    anchors = [
        (a, a.get("href", "").strip())
        for a in soup.find_all("a")
        if is_external(a.get("href", "").strip(), listing_url)
    ]
    if not anchors:
        return None

    # (1) vicinanza a un'etichetta esplicita. Si confronta la posizione nel testo
    # della pagina, non nel markup: le schede usano tabelle e il collegamento può
    # stare in una cella diversa da quella dell'etichetta.
    text = soup.get_text(" ", strip=True)
    labels = [m.end() for m in LINK_LABELS.finditer(text)]
    if labels:
        for anchor, href in anchors:
            label_text = " ".join((anchor.get_text(" ", strip=True) or "").split())
            position = text.find(label_text) if label_text else -1
            if position < 0:
                position = text.find(href)
            if position >= 0 and any(0 <= position - end <= LABEL_WINDOW for end in labels):
                return href

    # (2) ripiego: il primo esterno utile.
    return anchors[0][1]
