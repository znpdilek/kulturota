"""
Uygulama Konfigürasyonu
=======================
Pydantic-Settings ile env değişkenlerinden okuma yapan tek noktalı ayar nesnesi.
PRD Bölüm 7 & 16'ya göre PostgreSQL + PostGIS + Redis bağlantıları yönetilir.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Tüm uygulama ayarları .env dosyasından ya da ortam değişkenlerinden okunur."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Genel ---------------------------------------------------------------
    PROJECT_NAME: str = "KültürRota"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True

    # --- PostgreSQL (PRD 16) -------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "kulturrota"
    POSTGRES_USER: str = "kulturrota"
    POSTGRES_PASSWORD: str = "kulturrota_dev"

    # --- Redis (PRD 18) ------------------------------------------------------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # --- Pilot Bbox (PRD D1: İzmir) -----------------------------------------
    # Sıkı bbox: yalnızca İzmir ili koordinatlarını kapsar (kuzeyde Akhisar
    # gibi Manisa şehirlerini hariç tutmak için ince ayar yapılmıştır).
    PILOT_BBOX_MIN_LON: float = 26.10
    PILOT_BBOX_MIN_LAT: float = 37.78
    PILOT_BBOX_MAX_LON: float = 28.42
    PILOT_BBOX_MAX_LAT: float = 39.18

    # PRD §8.4 + D1 — İzmir il sınırlarına yaklaşık olan basitleştirilmiş
    # poligon (WGS84). Manisa il sınırına yapışan kuzey-doğu çıkıntılarını
    # (Akhisar/Soma vb.) açıkça dışarıda bırakır. ``ST_Within`` ile API
    # seviyesinde uygulanır (bkz. ``app.services.place_service``).
    IZMIR_BOUNDARY_WKT: str = (
        "POLYGON(("
        "26.93 39.18, 27.55 39.10, 27.55 38.55, 28.30 38.50, 28.40 38.10, "
        "28.10 37.85, 27.55 37.80, 27.20 37.95, 26.85 38.20, 26.30 38.30, "
        "26.18 38.45, 26.50 38.70, 26.80 38.95, 26.93 39.18"
        "))"
    )

    # --- KVKK (PRD D3) -------------------------------------------------------
    MIN_REGISTRATION_AGE_YEARS: int = 18

    # --- JWT (PRD §12.1 + §17.2) ---------------------------------------------
    # OAuth 2.0 + JWT (RS256 asimetrik). Access 15 dk, Refresh 30 gün rotating.
    # Anahtar çifti `app.core.keys` modülünde otomatik üretilir/okunur.
    JWT_ALGORITHM: Literal["RS256"] = "RS256"
    JWT_ISSUER: str = "kulturrota.api"
    JWT_AUDIENCE: str = "kulturrota.clients"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Rate Limiting (PRD §12.1) -------------------------------------------
    # Public: 60 req/dk, Auth: 300 req/dk — Redis token bucket.
    RATE_LIMIT_PUBLIC_PER_MIN: int = 60
    RATE_LIMIT_AUTH_PER_MIN: int = 300

    # --- CORS ---------------------------------------------------------------
    # Geliştirme: Vite dev server (5173) + lokal preview (4173).
    # Üretim: Vercel production domain(ler)i. Render üzerinde ortam değişkeni
    # olarak virgülle ayrılmış string biçiminde de verilebilir:
    #   CORS_ORIGINS="https://kulturota-brown.vercel.app,https://kulturrota-brown.vercel.app"
    # ``NoDecode`` ile pydantic-settings'in env değerini JSON olarak parse etme
    # adımı atlanır; bu sayede aşağıdaki ``field_validator`` ham string'i
    # alıp virgüle göre ayrıştırabilir.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:4173",
            "http://localhost:3000",
            # Üretim — Vercel domain'i (DİKKAT: gerçek alan adı tek 'r' ile
            # "kulturota-brown". Çift 'r' yazılı varyant da geriye dönük
            # uyumluluk için tutulur.)
            "https://kulturota-brown.vercel.app",
            "https://kulturrota-brown.vercel.app",
            "https://kulturota-a25p5kjqm-znpdileks-projects.vercel.app",
            "https://kulturrota-a25p5kjqm-znpdileks-projects.vercel.app",
        ]
    )

    # Vercel her PR/branch için yeni bir preview URL üretir
    # (ör. kulturota-brown-git-feature-foo.vercel.app). Tek tek listeye
    # eklemek yerine regex ile proje preview URL'lerini kabul ederiz.
    # Hem 'kulturota' (tek r) hem 'kulturrota' (çift r) yazımını eşler.
    CORS_ORIGIN_REGEX: str | None = Field(
        default=r"^https://kulturr?ota(-[a-z0-9-]+)*\.vercel\.app$",
        description=(
            "Origin için regex deseni. Vercel preview URL'lerini otomatik "
            "kabul etmek için kullanılır."
        ),
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, v: object) -> object:
        """Ortam değişkeninden gelen virgülle ayrılmış string'i listeye çevir.

        Render gibi PaaS'larda env değişkenleri sadece string olarak verildiği
        için ``"https://a.com,https://b.com"`` formatı da desteklenir. JSON
        array (``["..."]``) yine çalışır.
        """
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return v
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return v

    # --- Otonom AI Karar Katmanı (PRD §9) ------------------------------------
    # Birincil sağlayıcı: Google AI Studio — Gemini Flash (PRD §9.2).
    # Free-tier kotası: 15 RPM, 1.500 req/gün, 1M token/gün.
    GEMINI_API_KEY: str | None = Field(
        default=None,
        description=(
            "Google AI Studio API anahtarı (https://aistudio.google.com/app/apikey). "
            "Free-tier yeterlidir; mentor direktifi gereği ücretli plana geçilmez."
        ),
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.0-flash",
        description="PRD §9.2 birincil model. Alternatif: gemini-1.5-flash.",
    )
    GEMINI_API_BASE_URL: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        description="Google Generative Language REST endpoint base URL.",
    )

    # PRD §9.3 — Rate-limit yönetimi (mentor direktifi).
    # 15 RPM = 4 sn; 4.5 sn güvenli buffer.
    AI_RATE_LIMIT_SEC: float = 4.5
    # 1.500 req/gün limitine 100 buffer.
    AI_DAILY_QUOTA: int = 1400
    # 429 (RateLimit) durumunda kaç sn bekleyip yeniden denenecek.
    AI_RATE_LIMIT_BACKOFF_SEC: float = 60.0
    # HTTP zaman aşımı (saniye).
    AI_HTTP_TIMEOUT_SEC: float = 60.0

    # PRD §9.3 — Confidence eşiği.
    # ≥ 0.85 → otomatik uygula (merge/split/reject).
    # <  0.85 → kuyrukta tut, retry_count +1.
    AI_CONFIDENCE_THRESHOLD: float = 0.85
    # PRD §9.6 — 3 retry sonrası discard.
    AI_MAX_RETRY_COUNT: int = 3
    # Tek bir cron run'ında işlenecek maksimum kayıt sayısı.
    AI_BATCH_SIZE: int = 200

    # --- Medya / S3 / MinIO (PRD §13 — Medya ve Depolama Mimarisi) -----------
    # PRD §16: "Object Storage: S3 / MinIO — Foto + Bronze parquet".
    # Geliştirme ortamında **MinIO** (S3 uyumlu) kullanılır; üretimde gerçek
    # AWS S3'e geçildiğinde sadece endpoint ve credential değişir, kod aynı kalır.
    S3_ENDPOINT_URL: str | None = Field(
        default="http://localhost:9000",
        description=(
            "S3 uyumlu endpoint. MinIO (lokal): http://localhost:9000. "
            "AWS S3 için bu alanı boş bırakın → boto3 region URL'sini kullanır."
        ),
    )
    S3_REGION: str = Field(default="us-east-1", description="boto3 / S3 region.")
    S3_ACCESS_KEY: str = Field(default="kulturrota", description="MinIO/S3 access key.")
    S3_SECRET_KEY: str = Field(
        default="kulturrota_dev_secret",
        description="MinIO/S3 secret key. PROD: KMS/Vault üzerinden enjekte edin.",
    )
    S3_BUCKET_PHOTOS: str = Field(
        default="kulturrota-photos",
        description="Kullanıcı fotoğraflarının saklandığı bucket.",
    )
    # Path-style URL'ler MinIO için zorunludur (virtual-host yerine).
    S3_USE_PATH_STYLE: bool = Field(
        default=True,
        description="MinIO: True. AWS S3 prod: False (virtual-host-style).",
    )
    # Public CDN/HTTP base — MinIO için endpoint URL ile aynıdır.
    # AWS S3'te CloudFront / bucket public URL'ini gösterir.
    S3_PUBLIC_BASE_URL: str | None = Field(
        default="http://localhost:9000",
        description=(
            "Yüklenmiş fotoğrafların kullanıcıya sunulacağı public base URL. "
            "Boşsa endpoint_url'e fallback edilir."
        ),
    )

    # PRD §6.1 madde 7 + §17.4 — Upload Güvenliği.
    # Boyut sınırı: PRD §17.4 ImageMagick re-encode öncesi early-reject.
    MEDIA_MAX_BYTES: int = Field(
        default=5 * 1024 * 1024,
        description="Maksimum dosya boyutu (bayt). Varsayılan 5 MB.",
    )
    # İzinli MIME tipleri — magic-byte ile **çift kontrol** yapılır.
    MEDIA_ALLOWED_MIME: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png"],
        description="Whitelist MIME. .jpg ve .png kabul edilir (PRD direktifi).",
    )
    # PRD §17.3 + F3: EXIF GPS verisi yüklemeden önce **temizlenir**.
    # ETL/AI tarafına ihtiyaç olursa GPS *çıkarılabilir* (server-side log için);
    # ancak DB'ye yazılan exif blob asla GPS içermez.
    MEDIA_STRIP_EXIF: bool = True
    # Konum doğrulaması için EXIF GPS çıkarılır mı?
    # True olduğunda GPS koordinatı geri döner (DB'ye yazılmaz), False ise
    # tamamen ignore edilir.
    MEDIA_EXTRACT_GPS_FOR_VERIFICATION: bool = True

    # --- DB URL bileşik alanı -------------------------------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> str:
        """Senkron SQLAlchemy + psycopg2 için connection string."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg2",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Async SQLAlchemy + asyncpg için connection string."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> str:
        """Redis bağlantı stringi."""
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"rediss://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    """Settings nesnesini cache'lenmiş şekilde döndürür (FastAPI Depends uyumlu)."""
    return Settings()


settings = get_settings()
