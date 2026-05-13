"""
Bizizmir Açık Veri Extractor (CKAN)
===================================
PRD §8.1 #3: **D1 Pilot Kaynağı** — İzmir müzelerinin çalışma saatleri/günleri.
Lisans: **CC BY 4.0** — atıf zorunlu, kaynak + dataset adı + URL.

Portal CKAN üzerinde çalışır:
    * ``/api/3/action/package_search?q=...``  → ilgili dataset'leri keşfet
    * ``/api/3/action/package_show?id=...``    → resource listesi
    * ``/api/3/action/datastore_search?...``   → tablo halinde satırlar
    * (fallback) resource ``url`` üzerinden ham CSV/JSON indir

Bu modül, gerçek dataset slug'ı/sürümü değişebileceği için **dinamik keşif**
yapar; ``BIZIZMIR_SEARCH_QUERIES`` listesindeki anahtar kelimelerle eşleşen
dataset'leri çeker.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from etl.config import (
    BIZIZMIR_CKAN_BASE_URL,
    BIZIZMIR_SEARCH_QUERIES,
)
from etl.extract.base import (
    BronzeArtifact,
    ExtractError,
    http_client,
    write_bronze_snapshot,
)

logger = logging.getLogger(__name__)


_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)


def _ckan_call(client: httpx.Client, base_url: str, action: str, **params: Any) -> dict[str, Any]:
    """CKAN action API çağrısı için ufak yardımcı; ``success=False`` hatayı yutmaz."""
    url = f"{base_url.rstrip('/')}/api/3/action/{action}"
    try:
        resp = client.get(url, params=params)
    except _NETWORK_ERRORS as exc:
        raise ExtractError(f"Bizizmir network hatası ({action}): {exc}") from exc

    if resp.status_code != 200:
        raise ExtractError(
            f"Bizizmir CKAN {action} HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        body = resp.json()
    except ValueError as exc:
        raise ExtractError(f"Bizizmir CKAN {action} yanıtı JSON değil: {exc}") from exc

    if not body.get("success"):
        raise ExtractError(f"Bizizmir CKAN {action} success=False: {body.get('error')}")
    return body


def _fetch_resource_rows(client: httpx.Client, base_url: str, resource_id: str, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Bir resource'un satırlarını datastore_search ile çek."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        body = _ckan_call(
            client,
            base_url,
            "datastore_search",
            resource_id=resource_id,
            limit=limit,
            offset=offset,
        )
        records = body.get("result", {}).get("records", []) or []
        if not records:
            break
        rows.extend(records)
        if len(records) < limit:
            break
        offset += limit
        if offset > 50_000:
            logger.warning(
                "Bizizmir resource %s 50k satır limitine ulaştı, durduruldu.", resource_id
            )
            break
    return rows


def fetch(
    *,
    base_url: str = BIZIZMIR_CKAN_BASE_URL,
    search_queries: tuple[str, ...] = BIZIZMIR_SEARCH_QUERIES,
    persist_bronze: bool = True,
) -> tuple[dict[str, Any], BronzeArtifact | None]:
    """
    Bizizmir Açık Veri portalından İzmir kültürel mekan datasetlerini çek.

    Returns
    -------
    tuple
        ``(payload, bronze_artifact)`` — payload ``{"datasets": [...]}`` formatında;
        her dataset ``{"name", "title", "url", "resources": [{"id","url","records":[...]}]}``.

    Notlar
    -----
    * Kaynak portalı erişilemezse ``ExtractError`` fırlatılır, fakat **boş**
      ``datasets`` döndürmek üst katmana hata yutturmaz; bu yüzden orchestrator
      try/except ile sarmak isteyebilir.
    * D1 (Pilot) sözleşmesi gereği başka bir şehir verisi alınmaz.
    """
    logger.info("Bizizmir fetch başlıyor: base_url=%s queries=%s", base_url, list(search_queries))

    seen_dataset_names: set[str] = set()
    datasets: list[dict[str, Any]] = []

    with http_client() as client:
        for q in search_queries:
            try:
                result = _ckan_call(client, base_url, "package_search", q=q, rows=100)
            except ExtractError as exc:
                logger.warning("Bizizmir arama başarısız (q=%s): %s", q, exc)
                continue

            for pkg in result.get("result", {}).get("results", []):
                name = pkg.get("name")
                if not name or name in seen_dataset_names:
                    continue
                seen_dataset_names.add(name)

                resources: list[dict[str, Any]] = []
                for res in pkg.get("resources", []) or []:
                    res_id = res.get("id")
                    res_format = (res.get("format") or "").upper()
                    res_entry = {
                        "id": res_id,
                        "name": res.get("name"),
                        "format": res_format,
                        "url": res.get("url"),
                        "records": [],
                    }
                    # CKAN datastore varsa yapılandırılmış satırları al.
                    if res_id and res.get("datastore_active"):
                        try:
                            res_entry["records"] = _fetch_resource_rows(client, base_url, res_id)
                        except ExtractError as exc:
                            logger.warning(
                                "Bizizmir datastore_search başarısız (resource=%s): %s",
                                res_id,
                                exc,
                            )
                    resources.append(res_entry)

                datasets.append(
                    {
                        "name": name,
                        "title": pkg.get("title"),
                        "notes": pkg.get("notes"),
                        "license_id": pkg.get("license_id"),
                        "url": f"{base_url.rstrip('/')}/dataset/{name}",
                        "tags": [t.get("name") for t in pkg.get("tags", []) if t.get("name")],
                        "resources": resources,
                        "matched_query": q,
                    }
                )

    payload = {"datasets": datasets}
    record_count = sum(
        len(r.get("records") or []) for ds in datasets for r in ds.get("resources", [])
    )
    logger.info(
        "Bizizmir fetch tamamlandı: %d dataset, %d satır", len(datasets), record_count
    )

    artifact: BronzeArtifact | None = None
    if persist_bronze:
        artifact = write_bronze_snapshot(
            source="bizizmir",
            payload=payload,
            record_count=record_count,
            metadata={
                "endpoint": base_url,
                "queries": list(search_queries),
                "bbox": None,  # CKAN tarafından filtrelenmez; Silver'da geofence uygulanır.
                "license": "CC-BY-4.0",
                "attribution": "Bizizmir Açık Veri — © İzmir Büyükşehir Belediyesi",
            },
        )
    return payload, artifact


__all__ = ["fetch"]
