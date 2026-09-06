"""Pertinenza tematica, regione geografica e tipo di evento.

Il filtro è volutamente generoso su ciascuno dei due domini (fotonica, ML) e
premia chi li tocca entrambi: gli eventi di neuromorphic / optical computing
sono il bersaglio principale, ma una conferenza di sola fotonica o di solo ML
resta interessante e va tenuta, taggata, e lasciata filtrare dall'interfaccia.
"""

from __future__ import annotations

import re

# Termini pesati: 2 = molto specifico, 1 = generico ma indicativo.
PHOTONICS_TERMS: dict[str, int] = {
    "photonic": 2, "photonics": 2, "nanophotonic": 2, "optoelectronic": 2,
    "silicon photonics": 2, "integrated photonics": 2, "plasmonic": 2,
    "metasurface": 2, "metamaterial": 2, "waveguide": 2, "optical fiber": 2,
    "fibre optic": 2, "fiber optic": 2, "nonlinear optics": 2, "quantum optics": 2,
    "laser": 1, "lasers": 1, "optics": 1, "optical": 1, "optic": 1,
    "spectroscopy": 1, "interferometry": 1, "holography": 1, "polariton": 2,
    "microresonator": 2, "frequency comb": 2, "lidar": 1, "biophotonic": 2,
    "quantum photonic": 2, "light-matter": 2, "electro-optic": 2, "opto": 1,
}

ML_TERMS: dict[str, int] = {
    "neural network": 2, "neural networks": 2, "deep learning": 2,
    "machine learning": 2, "artificial intelligence": 1, "neuromorphic": 2,
    "reservoir computing": 2, "spiking neural": 2, "optical computing": 2,
    "photonic computing": 2, "analog computing": 2, "in-memory computing": 2,
    "ai accelerator": 2, "hardware accelerator": 1, "inference": 1,
    "transformer": 1, "computer vision": 1, "representation learning": 1,
    "generative model": 1, "foundation model": 1, "edge ai": 2,
    "brain-inspired": 2, "cognitive computing": 2, "tensor": 1, "backpropagation": 2,
}

# I termini che stanno esattamente sull'incrocio dei due campi.
CROSSOVER_TERMS = (
    "neuromorphic photonic", "photonic neural", "optical neural",
    "photonic computing", "optical computing", "reservoir computing",
    "photonic accelerator", "optical accelerator", "silicon photonics ai",
    "brain-inspired photonic", "neuromorphic computing", "photonic tensor",
)

QUANTUM_TERMS = ("quantum computing", "quantum optics", "quantum photonic", "qubit", "quantum information")
BIO_TERMS = ("biophotonic", "biomedical optics", "microscopy", "bioimaging", "optical coherence tomography")

SCHOOL_TERMS = ("summer school", "winter school", "spring school", "autumn school",
                "doctoral school", "phd school", "training school", "tutorial week", "école", "escuela")
WORKSHOP_TERMS = ("workshop", "hackathon", "seminar", "bootcamp", "tutorial")
SESSION_TERMS = ("special session", "special issue", "call for papers", "mini-symposium", "focus session")

#: Conferenze note per acronimo: il lessico non le riconoscerebbe mai dal solo titolo
#: ('NeurIPS 2026' non contiene alcuna parola tematica). Peso e tag sono espliciti.
KNOWN_ACRONYMS: dict[str, tuple[tuple[str, ...], int]] = {
    # fotonica / ottica
    "cleo": (("photonics",), 4),
    "ofc": (("photonics",), 4),
    "ecoc": (("photonics",), 4),
    "spie": (("photonics",), 3),
    "photonics west": (("photonics",), 4),
    "ipc": (("photonics",), 3),
    "frontiers in optics": (("photonics",), 4),
    "cleo europe": (("photonics",), 4),
    "eosam": (("photonics",), 4),
    "aps march meeting": (("photonics",), 2),
    "ecio": (("photonics",), 4),
    "ipr": (("photonics",), 3),
    "oecc": (("photonics",), 4),
    "acp": (("photonics",), 3),
    # machine learning
    "neurips": (("ml",), 4),
    "nips": (("ml",), 3),
    "icml": (("ml",), 4),
    "iclr": (("ml",), 4),
    "cvpr": (("ml",), 4),
    "iccv": (("ml",), 4),
    "eccv": (("ml",), 4),
    "aaai": (("ml",), 3),
    "ijcai": (("ml",), 3),
    "aistats": (("ml",), 3),
    "emnlp": (("ml",), 3),
    "acl": (("ml",), 2),
    "colt": (("ml",), 2),
    "uai": (("ml",), 2),
    # incrocio esplicito
    "iscas": (("ml", "photonics"), 2),
    "date conference": (("ml",), 2),
    "icons": (("ml", "neuromorphic"), 3),
    "nice conference": (("ml", "neuromorphic"), 3),
}

#: Paese/città → regione. Volutamente parziale: ciò che non si riconosce resta 'unknown'
#: invece di essere assegnato a caso.
_REGION_HINTS: dict[str, tuple[str, ...]] = {
    "europe": (
        "italy", "italia", "france", "germany", "deutschland", "spain", "españa", "portugal",
        "netherlands", "belgium", "austria", "switzerland", "sweden", "norway", "denmark",
        "finland", "poland", "czech", "hungary", "greece", "ireland", "uk", "united kingdom",
        "england", "scotland", "wales", "romania", "bulgaria", "croatia", "slovenia",
        "slovakia", "estonia", "latvia", "lithuania", "serbia", "iceland", "luxembourg",
        "cyprus", "malta", "milan", "milano", "rome", "roma", "turin", "torino", "florence",
        "firenze", "naples", "napoli", "venice", "venezia", "trento", "bologna", "pisa",
        "paris", "lyon", "nice", "grenoble", "toulouse", "marseille", "strasbourg",
        "berlin", "munich", "münchen", "hamburg", "frankfurt", "dresden", "aachen",
        "madrid", "barcelona", "valencia", "seville", "lisbon", "porto", "amsterdam",
        "eindhoven", "delft", "rotterdam", "brussels", "ghent", "leuven", "antwerp",
        "vienna", "graz", "zurich", "zürich", "geneva", "lausanne", "basel", "bern",
        "stockholm", "gothenburg", "oslo", "copenhagen", "helsinki", "warsaw", "krakow",
        "prague", "budapest", "athens", "dublin", "london", "cambridge", "oxford",
        "manchester", "edinburgh", "glasgow", "bristol", "southampton", "erice",
        "les houches", "trieste", "bari", "genoa", "genova", "palermo", "catania",
    ),
    "north-america": (
        "usa", "u.s.a", "united states", "canada", "mexico", "california", "texas",
        "new york", "boston", "san francisco", "san jose", "san diego", "los angeles",
        "seattle", "chicago", "denver", "austin", "atlanta", "washington", "vancouver",
        "toronto", "montreal", "ottawa", "quebec", "florida", "colorado", "arizona",
        "massachusetts", "michigan", "pennsylvania", "philadelphia", "baltimore",
        "new orleans", "las vegas", "orlando", "miami", "honolulu", "hawaii",
    ),
    "asia": (
        "china", "japan", "korea", "india", "singapore", "taiwan", "hong kong", "israel",
        "turkey", "türkiye", "uae", "emirates", "saudi", "qatar", "thailand", "vietnam",
        "malaysia", "indonesia", "philippines", "beijing", "shanghai", "shenzhen",
        "hangzhou", "wuhan", "tokyo", "osaka", "kyoto", "yokohama", "seoul", "busan",
        "delhi", "mumbai", "bangalore", "chennai", "hyderabad", "taipei", "tel aviv",
        "jerusalem", "haifa", "istanbul", "ankara", "dubai", "abu dhabi", "doha",
        "bangkok", "hanoi", "kuala lumpur", "jakarta", "manila", "phuket",
    ),
    "oceania": ("australia", "new zealand", "sydney", "melbourne", "brisbane", "perth",
                "canberra", "adelaide", "auckland", "wellington"),
    "africa": ("south africa", "egypt", "morocco", "tunisia", "kenya", "nigeria", "ghana",
               "cape town", "johannesburg", "cairo", "marrakech", "rabat", "nairobi", "kigali"),
    "south-america": ("brazil", "brasil", "argentina", "chile", "colombia", "peru", "uruguay",
                      "são paulo", "sao paulo", "rio de janeiro", "buenos aires", "santiago",
                      "bogota", "lima", "montevideo"),
    "online": ("online", "virtual", "remote", "webinar", "zoom", "hybrid"),
}


def _haystack(*parts: str | None) -> str:
    return " ".join(p.lower() for p in parts if p)


def _count(text: str, terms) -> tuple[int, list[str]]:
    """Somma i pesi dei termini presenti. Accetta dict pesato o sequenza (peso 2)."""
    weights = terms if isinstance(terms, dict) else {t: 2 for t in terms}
    score, hits = 0, []
    for term, weight in weights.items():
        # \b non funziona con termini che finiscono per '-'; usiamo un confine morbido.
        pattern = r"(?<![a-z])" + re.escape(term) + r"(?![a-z])"
        if re.search(pattern, text):
            score += weight
            hits.append(term)
    return score, hits


def detect_kind(title: str, description: str = "", fallback: str = "conference") -> str:
    text = _haystack(title, description)
    if any(t in text for t in SCHOOL_TERMS):
        return "school"
    if any(t in text for t in SESSION_TERMS):
        return "special-session"
    if any(t in text for t in WORKSHOP_TERMS):
        return "workshop"
    return fallback


def detect_region(location: str | None, title: str = "", description: str = "") -> str:
    """La location comanda; titolo e descrizione sono solo un ripiego."""
    for source_text in (location, _haystack(title, description)):
        if not source_text:
            continue
        text = source_text.lower()
        for region, hints in _REGION_HINTS.items():
            if any(re.search(r"(?<![a-z])" + re.escape(h) + r"(?![a-z])", text) for h in hints):
                return region
    return "unknown"


def score_event(title: str, description: str = "", location: str | None = None) -> dict:
    """Punteggio di pertinenza e tag tematici.

    Ritorna: {'score', 'topics', 'photonics', 'ml', 'relevant', 'hits'}
    """
    text = _haystack(title, description, location)
    photonics, p_hits = _count(text, PHOTONICS_TERMS)
    ml, m_hits = _count(text, ML_TERMS)
    crossover, c_hits = _count(text, CROSSOVER_TERMS)

    # Gli acronimi noti si cercano solo nel titolo: nella descrizione una sigla
    # come 'acl' o 'ipc' comparirebbe per caso troppo spesso.
    acr_hits: list[str] = []
    for acronym, (acr_topics, weight) in KNOWN_ACRONYMS.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(acronym) + r"(?![a-z0-9])", (title or "").lower()):
            acr_hits.append(acronym)
            if "photonics" in acr_topics:
                photonics += weight
                p_hits.append(acronym)
            if "ml" in acr_topics:
                ml += weight
                m_hits.append(acronym)
            if "neuromorphic" in acr_topics:
                crossover += weight
                c_hits.append(acronym)

    topics: list[str] = []
    if photonics:
        topics.append("photonics")
    if ml:
        topics.append("ml")
    # Il tag 'neuromorphic' si dà solo a chi sta davvero sull'incrocio: o un termine
    # esplicito, oppure entrambi i domini presenti in modo non marginale.
    if crossover or (photonics >= 2 and ml >= 2):
        topics.append("neuromorphic")
    if _count(text, QUANTUM_TERMS)[0]:
        topics.append("quantum")
    if _count(text, BIO_TERMS)[0]:
        topics.append("biophotonics")

    score = photonics + ml + crossover * 3
    if photonics and ml:
        score += 5  # sta su entrambi i campi: è esattamente ciò che si cerca

    return {
        "score": score,
        "topics": topics,
        "photonics": photonics,
        "ml": ml,
        "relevant": bool(photonics or ml),
        "hits": sorted(set(p_hits + m_hits + c_hits)),
    }
