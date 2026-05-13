"""Swagger / OpenAPI üretimini doğrula."""

from __future__ import annotations

import io
import sys

import httpx

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

r = httpx.get("http://127.0.0.1:8000/docs")
print(f"GET /docs        -> HTTP {r.status_code}, {len(r.text):,} bytes")

r = httpx.get("http://127.0.0.1:8000/openapi.json")
print(f"GET /openapi.json -> HTTP {r.status_code}")
spec = r.json()
print(f"OpenAPI version  : {spec.get('openapi')}")
print(f"API title        : {spec['info']['title']}  v{spec['info']['version']}")

print(f"\nKayıtlı uç sayısı: {len(spec['paths'])}\n")
for path, methods in sorted(spec["paths"].items()):
    for method, ep in methods.items():
        if method in ("get", "post", "put", "delete", "patch"):
            summary = ep.get("summary", "")
            print(f"  {method.upper():6} {path:32}  {summary}")

schemes = list(spec.get("components", {}).get("securitySchemes", {}).keys())
print(f"\nSecurity schemes : {schemes}")
