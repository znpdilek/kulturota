"""
Model Şeması Doğrulama Script'i
================================
Bu script:
    1. Tüm modelleri import eder.
    2. ``Base.metadata`` üzerinden CREATE TABLE DDL'lerini PostgreSQL diyalektine
       göre üretir.
    3. PRD Bölüm 10 & 11'de geçen tüm tabloların ve önemli constraint'lerin
       şemada bulunduğunu doğrular.

Çalıştırma:
    python scripts/verify_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_mock_engine

from app.db.base import Base


# PRD Bölüm 10'da geçen tüm tablolar
EXPECTED_TABLES = {
    "users",
    "places",
    "routes",
    "route_stops",
    "photos",
    "reviews",
    "favorites",
    "follows",
    "route_likes",
    "route_comments",
    "tags",
    "place_tags",
    "opening_hours",
    "ai_decision_queue",
    "ai_decision_log",
    "etl_run_log",
    "merge_decision_log",
    "audit_log",
    "reports",
}


def main() -> int:
    actual_tables = set(Base.metadata.tables.keys())

    missing = EXPECTED_TABLES - actual_tables
    extra = actual_tables - EXPECTED_TABLES

    print("=" * 70)
    print("Tablo Listesi Doğrulaması")
    print("=" * 70)
    for table in sorted(actual_tables):
        marker = "OK" if table in EXPECTED_TABLES else "EXTRA"
        print(f"  [{marker:>5}] {table}")
    print(f"\nToplam: {len(actual_tables)} tablo (PRD bekleniyor: {len(EXPECTED_TABLES)})")

    if missing:
        print(f"\nEKSİK TABLO(LAR): {missing}")
    if extra:
        print(f"\nFAZLA TABLO(LAR): {extra}")

    print("\n" + "=" * 70)
    print("Önemli Constraint Kontrolleri (PRD)")
    print("=" * 70)

    # 1. 18+ CHECK constraint (PRD D3)
    users = Base.metadata.tables["users"]
    user_checks = {c.name for c in users.constraints if c.__class__.__name__ == "CheckConstraint"}
    has_18plus = any("adult_birth_date" in n for n in user_checks)
    print(f"  [{'OK' if has_18plus else 'FAIL':>5}] users: 18+ CHECK constraint (D3)")

    # 2. UNIQUE(route_id, order_index) — PRD 11.1
    route_stops = Base.metadata.tables["route_stops"]
    rs_uniques = {tuple(c.columns.keys()) for c in route_stops.constraints if c.__class__.__name__ == "UniqueConstraint"}
    has_unique = ("route_id", "order_index") in rs_uniques
    print(f"  [{'OK' if has_unique else 'FAIL':>5}] route_stops: UNIQUE(route_id, order_index)")

    # 3. RouteStop place_id ON DELETE RESTRICT — PRD 11.1
    rs_place_fk = next(
        fk for fk in route_stops.foreign_keys if fk.column.table.name == "places"
    )
    print(
        f"  [{'OK' if rs_place_fk.ondelete == 'RESTRICT' else 'FAIL':>5}] "
        f"route_stops.place_id ON DELETE = {rs_place_fk.ondelete}"
    )

    # 4. Review place_id ON DELETE CASCADE — PRD 11.1
    reviews = Base.metadata.tables["reviews"]
    rv_place_fk = next(fk for fk in reviews.foreign_keys if fk.column.table.name == "places")
    print(
        f"  [{'OK' if rv_place_fk.ondelete == 'CASCADE' else 'FAIL':>5}] "
        f"reviews.place_id ON DELETE = {rv_place_fk.ondelete}"
    )

    # 5. Favorites bileşik PK — PRD 11.1
    favorites = Base.metadata.tables["favorites"]
    fav_pk = [c.name for c in favorites.primary_key.columns]
    print(f"  [{'OK' if set(fav_pk) == {'user_id', 'place_id'} else 'FAIL':>5}] favorites: composite PK = {fav_pk}")

    # 6. Follows bileşik PK + self ref — PRD 11.1
    follows = Base.metadata.tables["follows"]
    fol_pk = [c.name for c in follows.primary_key.columns]
    print(f"  [{'OK' if set(fol_pk) == {'follower_id', 'followee_id'} else 'FAIL':>5}] follows: composite PK = {fol_pk}")

    # 7. PostGIS Geography kolonları — PRD 10.1
    places = Base.metadata.tables["places"]
    koordinat_type = type(places.c.koordinat.type).__name__
    bbox_type = type(places.c.bbox.type).__name__
    has_geo = koordinat_type == "Geography" and bbox_type == "Geography"
    print(f"  [{'OK' if has_geo else 'FAIL':>5}] places.koordinat ({koordinat_type}) + places.bbox ({bbox_type})")

    # 8. Polimorfik reports — PRD 11.1 (FK YOK)
    reports = Base.metadata.tables["reports"]
    rep_target_fks = [fk for fk in reports.foreign_keys if fk.column.name == "target_id"]
    is_polymorphic = len(rep_target_fks) == 0
    print(f"  [{'OK' if is_polymorphic else 'FAIL':>5}] reports.target_id: polimorfik (FK sayısı = {len(rep_target_fks)})")

    # 9. Review rating CHECK 1-5
    rev_checks = {c.name for c in reviews.constraints if c.__class__.__name__ == "CheckConstraint"}
    has_rating = any("rating_range" in n for n in rev_checks)
    print(f"  [{'OK' if has_rating else 'FAIL':>5}] reviews: rating CHECK 1-5")

    # 10. Follow no_self_follow CHECK
    fol_checks = {c.name for c in follows.constraints if c.__class__.__name__ == "CheckConstraint"}
    has_nsf = any("no_self_follow" in n for n in fol_checks)
    print(f"  [{'OK' if has_nsf else 'FAIL':>5}] follows: no_self_follow CHECK")

    print("\n" + "=" * 70)
    print("DDL Üretimi (sadece syntax doğrulaması)")
    print("=" * 70)

    sql_lines: list[str] = []

    def dump(sql, *args, **kwargs):  # noqa: ANN001
        sql_lines.append(str(sql.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql://", dump)
    Base.metadata.create_all(engine, checkfirst=False)
    print(f"  Üretilen toplam DDL ifadesi: {len(sql_lines)}")
    print(f"  Toplam karakter: {sum(len(s) for s in sql_lines):,}")
    print("  (Hata yoksa tüm modeller PostgreSQL diyalektine sorunsuz derlendi.)")

    print("\n" + "=" * 70)
    print("PostgreSQL ENUM Tipleri (lowercase değerler kontrolü)")
    print("=" * 70)
    enum_lines = [
        s.strip() for s in sql_lines if "CREATE TYPE" in s.upper()
    ]
    for line in enum_lines:
        normalized = " ".join(line.split())
        print(f"  {normalized}")

    print()
    if missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
