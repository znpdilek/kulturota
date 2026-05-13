"""
Kategori Taksonomisi
====================
PRD §8.5 ``category_score`` için kaynak-spesifik etiketleri **kanonik** bir
kategori kümesine eşler. Aynı yapıyı (örn. "müze") farklı kaynaklar farklı
yazabildiği için, kategori-uyum skoru ancak ortak bir taksonomide anlamlıdır.

Kanonik kategori değerleri (PRD §10.1 ``places.kategori`` ile uyumlu):
    archaeological_site, ancient_city, castle, church, mosque, monument,
    museum, palace, religious_site, ruins, tomb, tower, ancient_artwork,
    archaeological_artifact, historic_district, historic_site, fort, agora,
    theatre, fountain, aqueduct, bath, library, synagogue, caravanserai.
"""

from __future__ import annotations

CANONICAL_CATEGORIES: frozenset[str] = frozenset(
    {
        "agora",
        "ancient_artwork",
        "ancient_city",
        "aqueduct",
        "archaeological_artifact",
        "archaeological_site",
        "bath",
        "caravanserai",
        "castle",
        "church",
        "fort",
        "fountain",
        "historic_district",
        "historic_site",
        "library",
        "monument",
        "mosque",
        "museum",
        "palace",
        "religious_site",
        "ruins",
        "synagogue",
        "theatre",
        "tomb",
        "tower",
    }
)


# ----------------------------------------------------------------------------
# OSM tag → canonical
# Format: ``"key=value"`` veya ``"key=*"`` (value-agnostic).
# ----------------------------------------------------------------------------
OSM_TAG_TO_CANONICAL: dict[str, str] = {
    # tourism=
    "tourism=museum": "museum",
    "tourism=gallery": "museum",
    "tourism=archaeological_site": "archaeological_site",
    "tourism=artwork": "ancient_artwork",
    # historic=
    "historic=castle": "castle",
    "historic=fort": "fort",
    "historic=monument": "monument",
    "historic=memorial": "monument",
    "historic=archaeological_site": "archaeological_site",
    "historic=ruins": "ruins",
    "historic=city_gate": "historic_site",
    "historic=tower": "tower",
    "historic=tomb": "tomb",
    "historic=aqueduct": "aqueduct",
    "historic=building": "historic_site",
    "historic=church": "church",
    "historic=mosque": "mosque",
    "historic=synagogue": "synagogue",
    "historic=palace": "palace",
    "historic=manor": "palace",
    "historic=fountain": "fountain",
    "historic=caravanserai": "caravanserai",
    "historic=baths": "bath",
    # building=
    "building=mosque": "mosque",
    "building=church": "church",
    "building=cathedral": "church",
    "building=synagogue": "synagogue",
    "building=castle": "castle",
    "building=tower": "tower",
    # amenity=
    "amenity=place_of_worship": "religious_site",
    "amenity=library": "library",
    "amenity=theatre": "theatre",
    "amenity=fountain": "fountain",
    # site_type= (arkeolojik kazı türleri)
    "site_type=ancient_theatre": "theatre",
    "site_type=agora": "agora",
    "site_type=aqueduct": "aqueduct",
    "site_type=bath": "bath",
    "site_type=fortification": "fort",
    "site_type=tumulus": "tomb",
    "site_type=tomb": "tomb",
    # heritage=*
    "heritage=*": "historic_site",
}


# ----------------------------------------------------------------------------
# Wikidata Q-ID → canonical
# ----------------------------------------------------------------------------
WIKIDATA_QID_TO_CANONICAL: dict[str, str] = {
    "Q33506": "museum",
    "Q207694": "museum",            # art museum
    "Q1248784": "museum",           # local museum
    "Q839954": "archaeological_site",
    "Q570116": "historic_site",     # tourist attraction (heritage filtreli)
    "Q15661340": "ancient_city",
    "Q44539": "religious_site",     # temple
    "Q12277": "monument",           # obelisk
    "Q16970": "church",
    "Q120560": "church",            # cathedral
    "Q32815": "mosque",
    "Q34627": "synagogue",
    "Q12518": "tower",
    "Q23413": "castle",
    "Q57821": "fort",
    "Q16560": "palace",
    "Q15243209": "historic_district",
    "Q24398318": "religious_site",
    "Q35112127": "historic_site",
    "Q2519064": "ruins",
    "Q133215": "monument",          # memorial
    "Q174782": "agora",             # square
    "Q482794": "agora",
    "Q1006257": "caravanserai",
    "Q570088": "fountain",
    "Q174814": "theatre",
    "Q24354": "theatre",
    "Q165896": "aqueduct",
    "Q22746": "bath",               # Roman bath
    "Q381885": "library",
    "Q43386": "tomb",               # mausoleum
}


def osm_tags_to_canonical(tags: dict[str, str] | None) -> list[str]:
    """
    OSM ``tags`` dict'inden kanonik kategori kümesi üret.

    Birden fazla eşleşme dönebilir (örn. ``historic=church`` + ``amenity=place_of_worship``).
    """
    if not tags:
        return []
    out: set[str] = set()
    for k, v in tags.items():
        if v is None:
            continue
        v_str = str(v)
        key_value = f"{k}={v_str}"
        if key_value in OSM_TAG_TO_CANONICAL:
            out.add(OSM_TAG_TO_CANONICAL[key_value])
            continue
        wildcard = f"{k}=*"
        if wildcard in OSM_TAG_TO_CANONICAL:
            out.add(OSM_TAG_TO_CANONICAL[wildcard])
    return sorted(out)


def osm_raw_categories(tags: dict[str, str] | None) -> list[str]:
    """Kaynaktan gelen orijinal etiketleri ``"key=value"`` formunda dön."""
    if not tags:
        return []
    relevant_keys = {
        "tourism", "historic", "building", "amenity",
        "site_type", "heritage", "religion", "denomination",
    }
    return sorted(
        f"{k}={v}" for k, v in tags.items() if k in relevant_keys and v is not None
    )


def wikidata_qids_to_canonical(qids: list[str] | str | None) -> list[str]:
    """
    Wikidata Q-ID listesinden kanonik kategori kümesi üret.

    ``qids`` ``"Q123|Q456"`` formatında string ya da liste olabilir.
    """
    if not qids:
        return []
    if isinstance(qids, str):
        qids = [q.strip() for q in qids.split("|") if q.strip()]
    out: set[str] = set()
    for q in qids:
        q_short = q.rsplit("/", 1)[-1]  # URI verilirse son segmenti al
        if q_short in WIKIDATA_QID_TO_CANONICAL:
            out.add(WIKIDATA_QID_TO_CANONICAL[q_short])
    return sorted(out)


__all__ = [
    "CANONICAL_CATEGORIES",
    "OSM_TAG_TO_CANONICAL",
    "WIKIDATA_QID_TO_CANONICAL",
    "osm_raw_categories",
    "osm_tags_to_canonical",
    "wikidata_qids_to_canonical",
]
