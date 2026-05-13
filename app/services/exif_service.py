"""
Görsel İşleme & EXIF Sanitization Servisi
=========================================
PRD §17.3 — KVKK: "Fotoğraflarda GPS verisi otomatik uçurulur".
PRD §17.4 — "Upload Güvenliği: MIME sniff, ClamAV sandbox, görsel re-encode".
PRD §14.3 (F3) — İstemci taraflı EXIF temizliği + perceptual hash + NSFW
filtreleri zinciri.

Bu modül yüklenen byte dizisi üzerinde **server-side** doğrulama yapar; çünkü
istemciye güvenmek (PRD §17.4) tehlikelidir:

1. **Magic byte doğrulaması**: MIME sniff. Sadece JPEG ve PNG kabul edilir.
2. **Pillow ile decode**: Bozuk/PNG-bomb saldırılarına karşı `Image.verify()`
   ardından gerçek decode denemesi.
3. **EXIF çıkarımı** (opsiyonel, PRD §17.3 + KVKK): GPS koordinatları konum
   *doğrulaması* için ayrı döndürülür; DB'ye yazılan blob asla GPS içermez.
4. **Re-encode (sanitization)**: PRD §17.4 — orijinal byte'ları doğrudan
   bucket'a koymak yerine Pillow ile **temiz** bir kopya üretir. Bu sayede
   gizli script/payload (ImageTragick benzeri) elenir.

Dışa aktarılan tek bir veri sınıfı (:class:`SanitizedImage`) vardır; üst
katman (`media_service`) bu sonuçla S3 yükleme + DB kaydı yapar.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError
from PIL.ExifTags import IFD

from app.core.config import settings
from app.core.exceptions import ProblemDetailsError

logger = logging.getLogger(__name__)


# --- Magic byte tablosu (PRD §17.4 MIME sniff) ------------------------------
# Whitelist edilmiş formatlar; PRD direktifi: ``.jpg`` ve ``.png``.
_MAGIC_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)

# Pillow `Image.format` → MIME normalizasyonu.
_PIL_FORMAT_TO_MIME: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
}

# Pillow tarafından decode edilebilecek maksimum piksel sayısı (PIL bomb).
# 24 MP üzeri görselleri reddet (DoS koruması).
Image.MAX_IMAGE_PIXELS = 24_000_000


@dataclass(slots=True)
class SanitizedImage:
    """:func:`sanitize_image` çıktısı.

    Bu sınıf yalnızca *değer nesnesi*dir; servis state'i tutmaz. Üst katman
    bunu doğrudan S3'e yükler, ardından DB satırını oluşturur.
    """

    cleaned_bytes: bytes
    """Re-encode edilmiş, EXIF'i temizlenmiş güvenli görsel byte'ları."""

    content_type: str
    """``image/jpeg`` veya ``image/png``."""

    extension: str
    """``jpg`` veya ``png`` (storage key suffix'i için)."""

    width: int
    height: int

    exif_sanitized: dict[str, Any] = field(default_factory=dict)
    """DB'ye yazılacak EXIF blob (GPS hariç). PRD §17.3."""

    taken_at: datetime | None = None
    """EXIF ``DateTimeOriginal``'dan üretilmiş ISO timestamp."""

    gps: dict[str, float] | None = None
    """Konum doğrulaması için EXIF'ten çıkarılan koordinat; DB'ye **yazılmaz**.
    PRD §17.3: GPS verisi yüklemeden önce temizlenir; bu alan opsiyonel
    doğrulama (mekan koordinatına uyum) içindir."""


# --- Public API ------------------------------------------------------------
def detect_mime_from_magic(data: bytes) -> str | None:
    """Magic byte ile MIME tahmini.

    İstemcinin gönderdiği `Content-Type` header'ına güvenmek yerine ilk
    8 byte'a bakarak doğrular. PRD §17.4 "MIME sniff".

    Args:
        data: Dosyanın ilk byte'ları (minimum 8 byte).

    Returns:
        MIME tipi veya `None` (whitelist dışı/bozuk).
    """
    for signature, mime, _ext in _MAGIC_SIGNATURES:
        if data.startswith(signature):
            return mime
    return None


def assert_size_within_limit(size_bytes: int) -> None:
    """PRD §17.4 + direktif: max 5MB.

    Multipart dosya boyutu API katmanında zaten okunuyor; ekstra koruma
    olarak servis seviyesinde de zorlanır.
    """
    if size_bytes <= 0:
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="Yüklenen dosya boş.",
            code="media.empty_file",
        )
    if size_bytes > settings.MEDIA_MAX_BYTES:
        limit_mb = settings.MEDIA_MAX_BYTES // (1024 * 1024)
        raise ProblemDetailsError(
            status=413,
            title="Payload Too Large",
            detail=f"Dosya boyutu {limit_mb} MB sınırını aşıyor.",
            code="media.file_too_large",
            extras={"limit_bytes": settings.MEDIA_MAX_BYTES},
        )


def sanitize_image(
    raw: bytes,
    *,
    declared_mime: str | None = None,
    extract_gps: bool | None = None,
) -> SanitizedImage:
    """Yüklenen byte dizisini doğrula, EXIF'i temizle ve güvenli kopya üret.

    Akış (PRD §14.3 / F3 + §17.4):

        1. Magic-byte doğrulama: sadece JPEG/PNG.
        2. Pillow ile decode (bozuk/payload reddi).
        3. EXIF'i parse et: GPS opsiyonel olarak ayrı döndürülür.
        4. Görseli RGB'ye dönüştür ve **EXIF'siz** olarak yeniden encode et.
        5. Sonuç byte dizisini :class:`SanitizedImage` olarak döndür.

    Args:
        raw: Multipart dosyasının tüm byte'ları.
        declared_mime: Multipart Content-Type (sadece çapraz kontrol için).
        extract_gps: ``None`` → settings default. PRD §17.3 + KVKK:
            yüklenen blob'a asla GPS yazılmaz; ancak server-side doğrulama
            için orijinal EXIF'ten okunabilir.

    Raises:
        ProblemDetailsError: 400 / 413 / 415 — KVKK ve güvenlik koruması.
    """
    if extract_gps is None:
        extract_gps = settings.MEDIA_EXTRACT_GPS_FOR_VERIFICATION

    # 1) Boyut sınırı (early reject) ---------------------------------------
    assert_size_within_limit(len(raw))

    # 2) Magic byte (PRD §17.4) --------------------------------------------
    sniffed_mime = detect_mime_from_magic(raw[:16])
    if sniffed_mime is None:
        raise ProblemDetailsError(
            status=415,
            title="Unsupported Media Type",
            detail="Sadece .jpg ve .png dosyaları kabul edilir.",
            code="media.unsupported_format",
        )
    if sniffed_mime not in settings.MEDIA_ALLOWED_MIME:
        raise ProblemDetailsError(
            status=415,
            title="Unsupported Media Type",
            detail=f"İzin verilen format dışı: {sniffed_mime}.",
            code="media.unsupported_format",
        )
    # Çapraz kontrol — istemci yalan söylerse logla (saldırı sinyali).
    if declared_mime and declared_mime.lower() not in {sniffed_mime, "application/octet-stream"}:
        logger.warning(
            "MIME uyumsuzluğu: declared=%s sniffed=%s", declared_mime, sniffed_mime
        )

    # 3) Pillow decode + verify --------------------------------------------
    try:
        # `verify()` stream'i tüketir → ardından yeniden açmamız gerekir.
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
    except (UnidentifiedImageError, Exception) as exc:  # noqa: BLE001
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="Görsel bozuk veya desteklenmeyen bir varyant.",
            code="media.decode_failed",
        ) from exc

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()  # Lazy decode'u zorla — bozuk EOF burada patlar.
    except Exception as exc:  # noqa: BLE001
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="Görsel decode edilemedi.",
            code="media.decode_failed",
        ) from exc

    pil_mime = _PIL_FORMAT_TO_MIME.get((image.format or "").upper())
    if pil_mime is None or pil_mime != sniffed_mime:
        raise ProblemDetailsError(
            status=415,
            title="Unsupported Media Type",
            detail="Görsel formatı doğrulanamadı.",
            code="media.format_mismatch",
        )

    # 4) EXIF parse + GPS opsiyonel çıkarımı -------------------------------
    exif_blob: dict[str, Any] = {}
    taken_at: datetime | None = None
    gps_payload: dict[str, float] | None = None

    raw_exif = None
    try:
        raw_exif = image.getexif()
    except Exception:  # noqa: BLE001
        raw_exif = None

    if raw_exif:
        # GPS verisi ayrı IFD'de tutulur — Pillow `getexif()`'in birinci
        # seviyesinde sadece offset olarak görünür. KVKK için (PRD §17.3)
        # önce yan tarafta okuyup *sonra* exif_blob inşasında atla.
        gps_ifd = None
        try:
            gps_ifd = raw_exif.get_ifd(IFD.GPSInfo)
        except Exception:  # noqa: BLE001
            gps_ifd = None
        if extract_gps and gps_ifd:
            gps_payload = _parse_gps_block(gps_ifd)

        for tag_id, value in raw_exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))

            # KVKK: GPSInfo blob'unu DB'ye asla yazma. (PRD §17.3)
            if tag_name == "GPSInfo":
                continue

            # DateTimeOriginal → ISO timestamp.
            if tag_name == "DateTimeOriginal" and isinstance(value, str):
                taken_at = _parse_exif_datetime(value)

            # Sadece JSON-serileştirilebilir skaler değerleri sakla.
            if isinstance(value, (int, float, str)):
                exif_blob[tag_name] = value

    # 5) Re-encode (sanitization, PRD §17.4) -------------------------------
    cleaned_bytes, content_type, extension = _reencode_clean(image, sniffed_mime)

    return SanitizedImage(
        cleaned_bytes=cleaned_bytes,
        content_type=content_type,
        extension=extension,
        width=image.width,
        height=image.height,
        exif_sanitized=exif_blob,
        taken_at=taken_at,
        gps=gps_payload,
    )


# --- Internal helpers -------------------------------------------------------
def _reencode_clean(image: Image.Image, mime: str) -> tuple[bytes, str, str]:
    """Görseli EXIF'siz olarak yeniden encode et.

    PRD §17.4: "görsel re-encode (ImageMagick)" — biz Pillow kullanırız.
    Çıktı, orijinal byte dizisinden bağımsız temiz bir kopyadır.
    """
    buf = io.BytesIO()
    target = image.copy()

    if mime == "image/jpeg":
        if target.mode not in ("RGB", "L"):
            target = target.convert("RGB")
        target.save(
            buf,
            format="JPEG",
            quality=88,
            optimize=True,
            progressive=True,
            exif=b"",
        )
        return buf.getvalue(), "image/jpeg", "jpg"

    if mime == "image/png":
        if target.mode not in ("RGB", "RGBA", "L", "LA"):
            target = target.convert("RGBA")
        target.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "image/png", "png"

    # Buraya düşmemesi gerekir — sniff aşamasında reddedildi.
    raise ProblemDetailsError(
        status=415,
        title="Unsupported Media Type",
        detail=f"Re-encode için desteklenmeyen format: {mime}.",
        code="media.unsupported_format",
    )


def _parse_exif_datetime(value: str) -> datetime | None:
    """``YYYY:MM:DD HH:MM:SS`` → :class:`datetime` (timezone naive)."""
    try:
        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _parse_gps_block(gps_info: dict[int, Any]) -> dict[str, float] | None:
    """EXIF GPSInfo blok'undan ``{"lat":..., "lng":..., "alt":...}`` üret.

    Args:
        gps_info: Pillow ``Image.getexif()[GPSInfo]`` çıktısı.

    Returns:
        ``{"lat": float, "lng": float, "alt": float?}`` veya ``None``
        (eksik/parse edilemeyen veri).
    """
    try:
        gps_data = {ExifTags.GPSTAGS.get(k, str(k)): v for k, v in gps_info.items()}
        lat_dms = gps_data.get("GPSLatitude")
        lat_ref = gps_data.get("GPSLatitudeRef")
        lng_dms = gps_data.get("GPSLongitude")
        lng_ref = gps_data.get("GPSLongitudeRef")

        if not (lat_dms and lat_ref and lng_dms and lng_ref):
            return None

        lat = _dms_to_decimal(lat_dms)
        lng = _dms_to_decimal(lng_dms)
        if lat is None or lng is None:
            return None

        if str(lat_ref).upper() == "S":
            lat = -lat
        if str(lng_ref).upper() == "W":
            lng = -lng

        result: dict[str, float] = {"lat": lat, "lng": lng}
        alt = gps_data.get("GPSAltitude")
        if alt is not None:
            try:
                result["alt"] = float(alt)
            except (TypeError, ValueError):
                pass
        return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("GPS parse hatası: %s", exc)
        return None


def _dms_to_decimal(dms: Any) -> float | None:
    """EXIF DMS (degrees, minutes, seconds) → ondalık derece.

    Pillow bunu genellikle ``IFDRational`` tuple olarak verir.
    """
    try:
        degrees, minutes, seconds = (float(x) for x in dms)
        return degrees + minutes / 60.0 + seconds / 3600.0
    except (TypeError, ValueError):
        return None
