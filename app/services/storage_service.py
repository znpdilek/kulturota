"""
S3 / MinIO Storage Servisi
==========================
PRD §13 — Medya ve Depolama Mimarisi.
PRD §16  — "Object Storage: S3 / MinIO".

Bu modül, kullanıcı fotoğraflarının (PRD 10.2 ``photos`` tablosu) bayt
dizilerini object store'a yazıp public URL'lerini üretir. Tek bir
:func:`get_storage_client` factory'sinden geçen ``boto3`` client'ı paylaşılır;
böylece her istekte yeni TCP/TLS açma maliyeti olmaz.

Tasarım notları
---------------
* **Soyutlama**: API katmanı yalnızca :class:`StorageService` ile konuşur.
  Sağlayıcı (MinIO ↔ AWS S3) değişimi tek satırlık `.env` güncellemesidir
  (bkz. ``S3_ENDPOINT_URL``).
* **MinIO uyumluluğu**: ``addressing_style="path"`` zorunludur; aksi halde
  istek ``bucket.localhost`` host'una düşer.
* **Bucket otomatik kurulumu**: Lokal geliştirmede `ensure_bucket()` çağrısı
  bucket yoksa oluşturur. Üretimde IaC (Terraform) bucket'ı sağlar; idempotent
  davrandığı için zarara yol açmaz.
* **Public URL üretimi**: PRD §13 — fotoğraf yükleme akışında DB'ye yazılan
  `url` alanı bu fonksiyonun çıktısıdır. CDN (Cloudflare/Bunny — PRD §18.1)
  arkasına alındığında ``S3_PUBLIC_BASE_URL`` ayarı değişir, kod aynıdır.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.exceptions import ProblemDetailsError

logger = logging.getLogger(__name__)


# --- Boto3 Client Factory --------------------------------------------------
@lru_cache(maxsize=1)
def get_s3_client():  # type: ignore[no-untyped-def]
    """Tek-instance boto3 S3 client'ı döndürür.

    `lru_cache` sayesinde tüm uygulama aynı bağlantı havuzunu paylaşır.
    `addressing_style="path"` MinIO için zorunludur; AWS S3'te de çalışır.

    Returns:
        ``botocore.client.S3`` — `put_object`, `head_object`, `create_bucket`…
    """
    config = Config(
        signature_version="s3v4",
        s3={
            "addressing_style": "path" if settings.S3_USE_PATH_STYLE else "virtual",
        },
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=10,
        read_timeout=30,
    )
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=config,
    )


# --- Storage Service Facade ------------------------------------------------
class StorageService:
    """API katmanının kullandığı sade fasad.

    Tek sorumluluk: byte dizisini bucket'a yaz, public URL döndür. NSFW skor,
    EXIF, thumbnail gibi sorumluluklar :mod:`app.services.media_service`
    içerisindedir; bu sınıf saf I/O katmanıdır.
    """

    def __init__(self, *, bucket: str | None = None) -> None:
        self.client = get_s3_client()
        self.bucket = bucket or settings.S3_BUCKET_PHOTOS

    # --- Bucket Lifecycle --------------------------------------------------
    def ensure_bucket(self) -> None:
        """Bucket yoksa oluşturur. Lokal geliştirme/test için idempotent.

        Üretimde IaC bu adımı üstlenir; yine de `head_bucket` çağrısı sağlıkla
        ilgili erken bilgi verir.
        """
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code not in ("404", "NoSuchBucket", "NoSuchBucketPolicy"):
                # Bilinmeyen hata: yetki, ağ, vb. → yukarı fırlat.
                logger.warning("head_bucket beklenmeyen hata: %s", exc)
                raise

        logger.info("Bucket bulunamadı, oluşturuluyor: %s", self.bucket)
        try:
            self.client.create_bucket(Bucket=self.bucket)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            # Yarış koşulu: birden fazla worker aynı anda yaratırsa "already
            # exists" hatasını gözardı et.
            if error_code not in (
                "BucketAlreadyOwnedByYou",
                "BucketAlreadyExists",
            ):
                raise

    # --- Object Operations -------------------------------------------------
    def upload_bytes(
        self,
        *,
        key: str,
        data: bytes | BinaryIO,
        content_type: str,
        cache_control: str = "public, max-age=604800",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Bayt dizisini bucket'a yaz ve public URL döndür.

        Args:
            key: Object key (ör. ``places/<uuid>/<uuid>.jpg``).
            data: Bytes veya seekable BinaryIO; boto3 her ikisini de kabul eder.
            content_type: ``image/jpeg``, ``image/png`` vb.
            cache_control: PRD §18.1 — CDN edge için TTL.
            metadata: User-metadata (`x-amz-meta-*`). PRD §13 atıf/license.

        Returns:
            Public erişim URL'i. PRD §13: bu URL ``photos.url`` alanına yazılır.
        """
        body: bytes | BinaryIO
        if isinstance(data, (bytes, bytearray)):
            body = bytes(data)
        else:
            body = data
            try:
                data.seek(0)
            except (AttributeError, OSError):
                # Stream rewind edilemiyorsa boto3 bir çağrıda tamamını okur.
                pass

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                CacheControl=cache_control,
                Metadata=metadata or {},
            )
        except ClientError as exc:
            logger.error("S3 put_object başarısız: bucket=%s key=%s err=%s",
                         self.bucket, key, exc)
            raise ProblemDetailsError(
                status=502,
                title="Bad Gateway",
                detail="Görsel depolama servisi şu an erişilemiyor.",
                code="media.storage_unavailable",
            ) from exc

        return self.build_public_url(key)

    def delete_object(self, key: str) -> None:
        """Yüklenmiş bir nesneyi sil (rollback senaryoları için)."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            # Silinemese de uygulama akışı durmamalı; sadece log.
            logger.warning("S3 delete_object başarısız: key=%s err=%s", key, exc)

    # --- URL Builder -------------------------------------------------------
    def build_public_url(self, key: str) -> str:
        """Public URL'i compose et.

        MinIO: ``http://localhost:9000/<bucket>/<key>``.
        AWS S3 (path-style off): ``https://<bucket>.s3.<region>.amazonaws.com/<key>``.
        CDN arkasındaysa: ``https://cdn.kulturrota.app/<key>`` (bucket gizli).
        """
        base = settings.S3_PUBLIC_BASE_URL or settings.S3_ENDPOINT_URL or ""
        base = base.rstrip("/")
        if settings.S3_USE_PATH_STYLE:
            return f"{base}/{self.bucket}/{key}"
        return f"{base}/{key}"


# --- DI Helper --------------------------------------------------------------
@lru_cache(maxsize=1)
def get_storage_service() -> StorageService:
    """FastAPI Depends / servisler için tek instance."""
    return StorageService()
