-- =============================================================================
-- KültürRota — PostgreSQL Eklentileri (PRD Bölüm 10 & 18)
-- =============================================================================

-- PostGIS: koordinat, bbox, ST_DWithin, ST_Within, GIST indeksleri
CREATE EXTENSION IF NOT EXISTS postgis;

-- citext: users.email ve users.username için case-insensitive UNIQUE
CREATE EXTENSION IF NOT EXISTS citext;

-- pgcrypto: gen_random_uuid() ve hashed search column (PRD 17.5)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- pg_trgm: name benzerlik araması (dedup yardımcısı, OpenSearch öncesi fallback)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
