# ETL Pipeline — KültürRota (Adım 2 · İzmir Pilot)

> **Referans:** PRD v2.0 · Bölüm 8 (Veri Kaynakları ve ETL Pipeline).
> **Kapsam:** Yalnızca **Extract**, **Normalize (Silver)** ve
> **Dedup / Gold + Queue yazımı**. Otonom AI Karar Katmanı (PRD §9, Adım 3)
> ve Apache Airflow / Prefect orkestrasyonu (PRD §8.7) bu adımın
> **dışındadır**.

---

## 1. Dizin Yapısı

```
etl/
├── __init__.py
├── README.md                   ← bu dosya
├── config.py                   ← bbox, eşikler, source-priority, endpoint'ler
├── bronze/                     ← ham snapshot partition'ları (gitignore'da)
├── extract/                    ← (Bronze input)
│   ├── base.py                 ← HTTP client + idempotency + snapshot yazıcısı
│   ├── overpass.py             ← OSM Overpass API
│   ├── wikidata.py             ← Wikidata SPARQL
│   └── bizizmir.py             ← Bizizmir Açık Veri (CKAN)
├── normalize/                  ← Silver: RawPlace kanonik şeması
│   ├── schema.py               ← @dataclass RawPlace
│   ├── text_utils.py           ← NFC, Türkçe casefold, HTML entity decode
│   ├── category_taxonomy.py    ← OSM/Wikidata → kanonik kategori eşleme
│   ├── overpass_normalizer.py
│   ├── wikidata_normalizer.py
│   └── bizizmir_normalizer.py
├── dedup/                      ← Gold: PRD §8.5 algoritması
│   ├── geohash.py              ← Saf-Python Geohash-7 encode/decode/neighbors
│   ├── scoring.py              ← Haversine + token-set ratio + kategori skoru
│   ├── merger.py               ← Source-priority alan birleştirme
│   └── deduper.py              ← Bloklama + DSU + eşik kuralları
├── load/                       ← DB yazımı
│   ├── etl_run.py              ← etl_run_log audit yardımcıları
│   ├── gold_writer.py          ← places + opening_hours + merge_decision_log
│   └── queue_writer.py         ← ai_decision_queue yazıcısı
└── pipelines/
    └── run_izmir_pilot.py      ← uçtan-uca İzmir orchestrator (CLI)
```

---

## 2. D1 Pilot Sözleşmesi

PRD §2 D1 ve §8.1: Tüm extract / normalize / dedup / load işlemleri
**yalnızca İzmir bbox** içinde çalışır:

```
bbox = (west=26.0, south=38.0, east=28.5, north=39.0)
```

Bu kutu `etl/config.py:IZMIR_BBOX` içinde **frozen** olarak tutulur. Faz-2'de
Türkiye genelini açmak için yeni bir `BoundingBox` örneği geçilir — kod
değişmez (PRD §8.1 notu).

---

## 3. Bronze Katmanı (PRD §8.3)

Her extract çağrısı, **hiçbir dönüşüm uygulamadan** ham payload'ı
`etl/bronze/source=<x>/yyyy=YYYY/mm=MM/dd=DD/<idempotency_key>.json`
şemasında diske yazar. Envelope iki bloktan oluşur:

```jsonc
{
  "metadata": {
    "endpoint": "https://overpass-api.de/api/interpreter",
    "query": "...QL...",
    "bbox": { "west": 26.0, ... },
    "license": "ODbL-1.0",
    "attribution": "© OpenStreetMap contributors",
    "idempotency_key": "overpass:abc123..."
  },
  "data": { "elements": [ ... ] }
}
```

Aynı (source, query, bbox) tripletini paylaşan re-run'lar aynı dosya yoluna
yazar — operasyon **idempotent** (PRD §8.3).

---

## 4. Silver Katmanı (PRD §8.4)

Tüm kaynaklardan gelen kayıtlar `etl.normalize.RawPlace` kanonik şemasına
eşlenir. Uygulanan kurallar:

| Kural | Uygulama |
| --- | --- |
| Unicode NFC | `text_utils.normalize_text` |
| Türkçe casefold | `text_utils.tr_casefold` (`İ→i`, `I→ı`) |
| HTML entity decode | `html.unescape` |
| `lat/lon` zorunlu | yoksa **discard** |
| İzmir bbox geofence | yoksa **discard** |
| Name eksik | `RawPlace.has_required_fields = False` + `missing_field_reasons += ["name"]` |
| Çok-dilli isim | OSM `name:tr/en/de/fr/ar`, Wikidata `rdfs:label@*` |
| Kategori taksonomisi | `category_taxonomy.osm_tags_to_canonical` / `wikidata_qids_to_canonical` |

---

## 5. Gold Katmanı — Dedup (PRD §8.5)

Algoritma `etl.dedup.deduper.dedup_records`:

```
1. Geohash-7 bloklama (~150m × 150m) — opsiyonel olarak komşu blokları da kıyasla.
2. Pairwise skor (etl.dedup.scoring.pairwise_score):
       total = 0.45 * geo_score
             + 0.35 * name_score    (RapidFuzz token-set ratio, Türkçe normalize)
             + 0.20 * category_score (canonical taksonomi overlap coefficient)
3. Union-Find: ``score >= 0.90`` kenarlardan deterministic cluster oluştur.
4. Cluster içi `merge_cluster` — alan-bazlı source-priority:
       koordinat → OSM
       isim      → Wikidata
       tescil    → Kültür Portalı / Wikidata
       opening_hours → Bizizmir
       kapak     → Wikidata (Wikimedia Commons)
5. ``0.60 <= score < 0.90`` kenarlar farklı cluster'lardaysa →
   ``ai_decision_queue`` (Adım 3'te AI işleyecek).
6. ``score < 0.60`` → ayrı kayıt; eksik veri varsa discard.
```

Eşikler `etl/config.py` üzerinden okunur:
* `AUTO_MERGE_THRESHOLD = 0.90`
* `QUEUE_THRESHOLD = 0.60`

`geo_score` formülü PRD §8.5 ile birebir: `1 / (1 + d_m / 50)`. Bu **kasıtlı
olarak tutucu**dur — kaynaklar-arası koordinat farkı 50 m'yi aştıkça geo
skoru hızla düşer; mesafe ~150 m'yi geçtiğinde auto-merge gerçekleşmez ve
çift AI Karar Katmanı'na devredilir (PRD §9.4 örneği bu davranışı somutlaştırır).

`category_score` taksonomi **overlap coefficient**ı kullanır
(`|A∩B| / min(|A|, |B|)`); Jaccard yerine overlap seçimi, kaynakların
**farklı granülaritede** kategori vermesini cezalandırmaz (örn. Wikidata
`{archaeological_site, ancient_city}` ↔ OSM `{archaeological_site}` →
overlap = 1.0).

---

## 6. Çalıştırma

### 6.1 Tek seferde uçtan uca

```bash
# .env içinde DB ayarları doğru olmalı + alembic upgrade head çalıştırılmış olmalı
python -m etl.pipelines.run_izmir_pilot
```

### 6.2 Sadece bir kaynak

```bash
python -m etl.pipelines.run_izmir_pilot --only overpass
python -m etl.pipelines.run_izmir_pilot --only wikidata --only bizizmir
```

### 6.3 DB olmadan (dry-run, sadece Bronze + Silver + Dedup raporu)

```bash
python -m etl.pipelines.run_izmir_pilot --skip-load
```

### 6.4 Tamamen ağdan bağımsız smoke-test

```python
from etl.dedup.geohash import encode, neighbors
from etl.dedup.scoring import pairwise_score
from etl.normalize.schema import RawPlace

a = RawPlace(source="osm", source_id="node/1",
             name_tr="Efes Antik Kenti", lat=37.94, lng=27.34,
             canonical_categories=["archaeological_site"])
b = RawPlace(source="wikidata", source_id="Q43332",
             name_tr="Efes", name_en="Ephesus", lat=37.939, lng=27.342,
             canonical_categories=["archaeological_site", "ancient_city"])

print(encode(a.lat, a.lng))             # 'sw5sptg' (örnek)
print(pairwise_score(a, b))             # total ≈ 0.97 → otomatik merge
```

---

## 7. DB Yazım Şeması

| Cluster türü | Hedef tablo | Lineage |
| --- | --- | --- |
| `score >= 0.90` cluster (≥1 üye) | `places` + `opening_hours` | `merge_decision_log` (alan-bazlı kaynak özeti) |
| Singleton (bloktaki tek kayıt) | `places` + `opening_hours` | `merge_decision_log` (`decision='auto_insert'`) |
| `0.60 ≤ score < 0.90` çift | `ai_decision_queue` | `reason='low_confidence'` |
| Eksik koordinat / isim | discard (sadece log) | — |

Her pipeline çalıştırması `etl_run_log` tablosuna **idempotency_key** ile
yazılır; aynı gün ikinci kez çalıştırma audit izini bozmaz (PRD §8.3).

---

## 8. Sınırlar ve Sonraki Adımlar

Bu adım (Adım 2) için **kapsam dışı**:

* **Adım 3** — Otonom AI Karar Katmanı (PRD §9): `ai_decision_queue`
  satırlarını gece cron worker'ı ile Gemini / Groq free-tier API'ye gönderme.
* **Apache Airflow / Prefect** DAG'ları (PRD §8.7) — şimdilik bu pipeline
  manuel Python invocation ile veya basit `cron` ile çalıştırılır.
* **LLM ile Türkçe çeviri batch'i** (PRD §9.5, D5) — Adım 3'ün parçası.
* **Great Expectations** DQ raporu (PRD §8.6) — Adım 4.
* **Kültür Portalı scraper** (PRD §8.1 #4) — robots.txt + rate-limit ile
  Faz-1'in sonraki iterasyonu.

---

## 9. Lisans ve Atıf (PRD §20)

| Kaynak | Lisans | Uygulama |
| --- | --- | --- |
| OSM (Overpass) | **ODbL-1.0** | `kaynak_atif[].license = "ODbL-1.0"`; Bronze metadata'da `attribution = "© OpenStreetMap contributors"` |
| Wikidata | **CC0-1.0** | atıf zorunlu değil ama yine de korunur |
| Bizizmir Açık Veri | **CC-BY-4.0** | atıf bloğu + dataset URL'i |
| Wikipedia kapak görseli | CC0 / CC-BY-SA | `places.kapak_foto_url` (Wikimedia Commons resolver URL'i) |

`etl.normalize.RawPlace.attribution_block()` ile her ham kaydın atıf satırı
otomatik üretilir ve `places.kaynak_atif` JSONB alanına yazılır.
