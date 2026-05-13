"""ETL Smoke Test — sadece tüm modüllerin import edilebildiğini ve dedup
algoritmasının çıplak akışının çalıştığını doğrular."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    log_path = PROJECT_ROOT / "etl_smoke.log"
    out: list[str] = []

    def step(name: str) -> None:
        out.append(f"[ok] {name}")

    try:
        # 1. Import zincirinin tamamı.
        import etl  # noqa: F401
        from etl import config
        from etl.extract import base, overpass, wikidata, bizizmir  # noqa: F401
        from etl.normalize import (
            schema,
            text_utils,
            category_taxonomy,
            overpass_normalizer,
            wikidata_normalizer,
            bizizmir_normalizer,
        )  # noqa: F401
        from etl.dedup import geohash, scoring, merger, deduper

        step("etl, extract, normalize, dedup modülleri import edildi")

        # 2. Bbox kontratı.
        assert config.IZMIR_BBOX.west == 26.0
        assert config.IZMIR_BBOX.south == 38.0
        assert config.IZMIR_BBOX.east == 28.5
        assert config.IZMIR_BBOX.north == 39.0
        assert config.IZMIR_BBOX.contains(38.42, 27.14) is True  # İzmir merkez
        assert config.IZMIR_BBOX.contains(41.0, 29.0) is False  # İstanbul
        step("D1: IZMIR_BBOX değerleri ve geofence doğru")

        # 3. Geohash.
        gh = geohash.encode(38.42, 27.14, precision=7)
        assert len(gh) == 7 and all(c in "0123456789bcdefghjkmnpqrstuvwxyz" for c in gh)
        assert len(geohash.neighbors(gh)) == 8
        s, w, n, e = geohash.decode_bbox(gh)
        assert s < 38.42 < n and w < 27.14 < e
        step(f"geohash-7 encode/decode/neighbors çalışıyor (örnek={gh})")

        # 4. Skor formülleri.
        d = scoring.haversine_m(38.42, 27.14, 38.42, 27.14)
        assert abs(d) < 1e-6
        g0 = scoring.geo_score(38.42, 27.14, 38.42, 27.14)
        assert abs(g0 - 1.0) < 1e-6, "Aynı noktada geo_score=1.0 olmalı"
        g_far = scoring.geo_score(38.0, 26.0, 39.0, 28.5)
        assert g_far < 0.01, f"Uzak noktalarda geo_score düşük olmalı (got {g_far})"
        step(f"haversine + geo_score doğru (uzak={g_far:.4f})")

        # 5. Pairwise skor — gerçekçi cross-source koordinat farkı (~10 m) → AUTO-MERGE.
        # OSM ve Wikidata aynı POI için tipik olarak 5-30 m içinde koordinat
        # verir (centroid vs ana giriş farkı). PRD §8.5 ``/ 50`` softening'i ile
        # auto-merge eşiği (≥ 0.90), yalnızca bu sıkı yakınlık için tetiklenir.
        from etl.normalize.schema import RawPlace

        a = RawPlace(
            source="osm",
            source_id="node/123",
            name_tr="Efes Antik Kenti",
            name_en="Ephesus",
            lat=37.94093,
            lng=27.34168,
            canonical_categories=["archaeological_site"],
        )
        b = RawPlace(
            source="wikidata",
            source_id="Q43332",
            name_tr="Efes",
            name_en="Ephesus",
            lat=37.94100,
            lng=27.34175,
            canonical_categories=["archaeological_site", "ancient_city"],
            wikidata_id="Q43332",
        )
        sp = scoring.pairwise_score(a, b)
        assert sp.total >= config.AUTO_MERGE_THRESHOLD, (
            f"Çok yakın aynı isim → total≥0.90 beklenir (got {sp.total:.3f})"
        )
        step(
            f"pairwise_score yakın çift (~{sp.distance_m:.1f} m): "
            f"total={sp.total:.3f}, geo={sp.geo:.3f}, name={sp.name:.3f}, cat={sp.category:.3f}"
        )

        # 5b. PRD §9.4'ün **kendi prompt örneği** — koordinatlar ~207 m farklı.
        # PRD bu çifti AI Karar Katmanı için kasıtlı seçmiştir: auto-merge
        # YERINE ai_decision_queue'ya düşmesi beklenir (0.60 ≤ s < 0.90).
        a_queue = RawPlace(
            source="osm",
            source_id="node/9001",
            name_tr="Efes Antik Kenti",
            name_en="Ephesus",
            lat=37.94,
            lng=27.34,
            canonical_categories=["archaeological_site"],
        )
        b_queue = RawPlace(
            source="wikidata",
            source_id="Q43332",
            name_tr="Efes",
            name_en="Ephesus",
            lat=37.939,
            lng=27.342,
            canonical_categories=["archaeological_site", "ancient_city"],
            wikidata_id="Q43332",
        )
        sp_q = scoring.pairwise_score(a_queue, b_queue)
        assert config.QUEUE_THRESHOLD <= sp_q.total < config.AUTO_MERGE_THRESHOLD, (
            f"PRD §9.4 örneği (~{sp_q.distance_m:.0f} m): queue aralığında "
            f"[{config.QUEUE_THRESHOLD}, {config.AUTO_MERGE_THRESHOLD}) beklenir (got {sp_q.total:.3f})"
        )
        step(
            f"pairwise_score PRD §9.4 örneği (~{sp_q.distance_m:.0f} m): "
            f"total={sp_q.total:.3f} → ai_decision_queue (AI'ya devir)"
        )

        # 6. Farklı şehir / farklı isim → 0.60 altı (separate).
        c = RawPlace(
            source="osm",
            source_id="node/9",
            name_tr="Konak Pier",
            lat=38.43,
            lng=27.13,
            canonical_categories=["historic_site"],
        )
        sp2 = scoring.pairwise_score(a, c)
        assert sp2.total < config.QUEUE_THRESHOLD, (
            f"İzmir merkez ile Efes ayrı kayıt olmalı (got {sp2.total:.3f})"
        )
        step(f"pairwise_score uzak çift: total={sp2.total:.3f} (< {config.QUEUE_THRESHOLD})")

        # 7. Dedup ucu uca.
        records = [
            a,         # OSM Efes — sıkı
            b,         # Wikidata Efes — sıkı (a ile auto-merge cluster oluşturur)
            c,         # Konak Pier (singleton)
            a_queue,   # PRD §9.4 OSM Efes — geniş (queue kandidatı)
            b_queue,   # PRD §9.4 Wikidata Efes — geniş (queue kandidatı)
        ]
        result = deduper.dedup_records(records)
        assert len(result.clusters) >= 1
        merged = next((cl for cl in result.clusters if not cl.is_singleton), None)
        assert merged is not None, "En az bir cluster (sıkı Efes auto-merge) beklenir"
        assert len(merged.members) >= 2
        step(
            f"dedup_records: {len(result.clusters)} cluster, "
            f"{len(result.queued_pairs)} queue, {len(result.discarded)} discard"
        )

        # 8. Kategori taksonomisi.
        cats = category_taxonomy.osm_tags_to_canonical({"tourism": "museum"})
        assert cats == ["museum"], cats
        cats_q = category_taxonomy.wikidata_qids_to_canonical("Q23413|Q33506")
        assert set(cats_q) == {"castle", "museum"}, cats_q
        step("kategori taksonomisi doğru")

        # 9. Text utilities — Türkçe casefold.
        s = text_utils.tr_casefold("İZMİR")
        assert s == "izmir", repr(s)
        s2 = text_utils.normalize_for_match("Efes &amp; Antik Kenti")
        assert "efes" in s2 and "antik" in s2
        step(f"text_utils Türkçe casefold doğru (örnek={s})")

        # 10. Idempotency key deterministic.
        from etl.extract.base import idempotency_key

        k1 = idempotency_key("overpass", {"bbox": [26, 38, 28.5, 39]})
        k2 = idempotency_key("overpass", {"bbox": [26, 38, 28.5, 39]})
        assert k1 == k2, "idempotency_key deterministik olmalı"
        step(f"idempotency_key deterministik ({k1})")

        # 11. Source priority merge — Wikidata isim, OSM koordinat.
        canonical, lineage = merger.merge_cluster([a, b])
        assert canonical.lat == a.lat  # OSM koordinatı kazandı (priority)
        assert canonical.name_en == "Ephesus"
        assert canonical.wikidata_id == "Q43332"
        assert lineage["koordinat"] == "osm"
        step(f"merge_cluster source-priority doğru (lineage={lineage})")

        out.append("")
        out.append("=" * 60)
        out.append("ETL SMOKE OK")
        out.append("=" * 60)
        log_path.write_text("\n".join(out), encoding="utf-8")
        print("\n".join(out))
        return 0

    except Exception as exc:  # noqa: BLE001
        out.append("")
        out.append("[FAIL] " + str(exc))
        out.append(traceback.format_exc())
        log_path.write_text("\n".join(out), encoding="utf-8")
        print("\n".join(out))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
