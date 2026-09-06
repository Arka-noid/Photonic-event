from collector.relevance import detect_kind, detect_region, score_event


def test_evento_sullincrocio_batte_quelli_di_un_solo_campo():
    crossover = score_event("International Conference on Neuromorphic Photonics")
    solo_fotonica = score_event("Conference on Laser Spectroscopy")
    assert crossover["score"] > solo_fotonica["score"]
    assert "neuromorphic" in crossover["topics"]


def test_conferenze_note_solo_per_acronimo_vengono_riconosciute():
    # Senza la tabella acronimi 'NeurIPS 2026' non contiene nessuna parola del
    # lessico e verrebbe scartata come non pertinente.
    for acronym, topic in [("NeurIPS 2026", "ml"), ("ICML 2026", "ml"), ("CLEO 2026", "photonics"), ("OFC 2027", "photonics")]:
        result = score_event(acronym)
        assert result["relevant"], acronym
        assert topic in result["topics"], acronym


def test_eventi_fuori_tema_vengono_scartati():
    for title in ["Annual Meeting of the Cake Society", "Workshop on Municipal Waste Management"]:
        assert not score_event(title)["relevant"], title


def test_acronimi_cercati_solo_nel_titolo():
    # 'acl' nella descrizione di un evento di ortopedia non deve renderlo pertinente.
    assert not score_event("Knee Surgery Symposium", "repair of the acl ligament")["relevant"]


def test_regione_dalla_location_e_fallback_a_unknown():
    assert detect_region("Milan, Italy") == "europe"
    assert detect_region("San Jose, CA, USA") == "north-america"
    assert detect_region("Tokyo, Japan") == "asia"
    assert detect_region(None, "Fully online workshop") == "online"
    assert detect_region("Atlantis") == "unknown"


def test_la_location_ha_la_precedenza_sul_titolo():
    assert detect_region("Boston, USA", "European Optical Society Meeting") == "north-america"


def test_tipo_evento_dal_titolo():
    assert detect_kind("Summer School on Photonics") == "school"
    assert detect_kind("Workshop on Optical AI") == "workshop"
    assert detect_kind("Special session on photonic computing") == "special-session"
    assert detect_kind("IEEE Photonics Conference") == "conference"
