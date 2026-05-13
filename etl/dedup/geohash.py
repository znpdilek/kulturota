"""
Geohash Encoder (Saf Python)
============================
PRD §8.5 #1: "Block by Geohash-7 (≈ 150m × 150m grid)".

Bu modül, üçüncü-parti bağımlılık eklemeden Geohash kodlamasını uygular.
Doğrulama referansı için: https://en.wikipedia.org/wiki/Geohash

Geohash-7 doğruluğu:
    * ~152 m enlem
    * ~152 m boylam (ekvatorda); İzmir'in ~38° kuzey enleminde ~120 m.
    * Aynı 7-karakter geohash'i paylaşan iki nokta KESİNLİKLE 150m × 150m
      bir kutucukta yer alır → pairwise karşılaştırma bu blokla sınırlanır.
"""

from __future__ import annotations

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_BASE32_INDEX = {c: i for i, c in enumerate(_BASE32)}


def encode(lat: float, lng: float, precision: int = 7) -> str:
    """
    ``(lat, lng)`` çiftini verilen hassasiyette Geohash string'ine dönüştür.

    Examples
    --------
    >>> encode(37.94, 27.34, precision=7)
    'sw5sptg'
    >>> len(encode(38.42, 27.14, precision=7))
    7
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"lat aralık dışı: {lat}")
    if not -180.0 <= lng <= 180.0:
        raise ValueError(f"lng aralık dışı: {lng}")
    if precision < 1:
        raise ValueError("precision >= 1 olmalı")

    lat_lo, lat_hi = -90.0, 90.0
    lng_lo, lng_hi = -180.0, 180.0
    bits: list[int] = []
    chars: list[str] = []
    even = True

    while len(chars) < precision:
        if even:
            mid = (lng_lo + lng_hi) / 2.0
            if lng >= mid:
                bits.append(1)
                lng_lo = mid
            else:
                bits.append(0)
                lng_hi = mid
        else:
            mid = (lat_lo + lat_hi) / 2.0
            if lat >= mid:
                bits.append(1)
                lat_lo = mid
            else:
                bits.append(0)
                lat_hi = mid
        even = not even

        if len(bits) == 5:
            idx = (
                (bits[0] << 4)
                | (bits[1] << 3)
                | (bits[2] << 2)
                | (bits[3] << 1)
                | bits[4]
            )
            chars.append(_BASE32[idx])
            bits = []

    return "".join(chars)


def decode_bbox(geohash: str) -> tuple[float, float, float, float]:
    """
    Geohash string'i çevreleyen kutuyu ``(south, west, north, east)`` döner.
    """
    if not geohash:
        raise ValueError("geohash boş olamaz")

    lat_lo, lat_hi = -90.0, 90.0
    lng_lo, lng_hi = -180.0, 180.0
    even = True

    for ch in geohash:
        idx = _BASE32_INDEX.get(ch)
        if idx is None:
            raise ValueError(f"Geçersiz geohash karakteri: {ch!r}")
        for bit_pos in (4, 3, 2, 1, 0):
            bit = (idx >> bit_pos) & 1
            if even:
                mid = (lng_lo + lng_hi) / 2.0
                if bit == 1:
                    lng_lo = mid
                else:
                    lng_hi = mid
            else:
                mid = (lat_lo + lat_hi) / 2.0
                if bit == 1:
                    lat_lo = mid
                else:
                    lat_hi = mid
            even = not even

    return lat_lo, lng_lo, lat_hi, lng_hi


def neighbors(geohash: str) -> list[str]:
    """
    Bir geohash'in 8 komşusunu döner. Sınır kayıtlarını yakalamak için
    PRD §8.5 önerisi: aynı blok + komşu blokları birlikte karşılaştır.
    """
    if not geohash:
        return []
    lat_lo, lng_lo, lat_hi, lng_hi = decode_bbox(geohash)
    lat_mid = (lat_lo + lat_hi) / 2.0
    lng_mid = (lng_lo + lng_hi) / 2.0
    lat_step = lat_hi - lat_lo
    lng_step = lng_hi - lng_lo
    p = len(geohash)

    deltas = [
        (+lat_step, -lng_step),
        (+lat_step, 0.0),
        (+lat_step, +lng_step),
        (0.0, -lng_step),
        (0.0, +lng_step),
        (-lat_step, -lng_step),
        (-lat_step, 0.0),
        (-lat_step, +lng_step),
    ]

    out: list[str] = []
    for dlat, dlng in deltas:
        n_lat = lat_mid + dlat
        n_lng = lng_mid + dlng
        if -90.0 <= n_lat <= 90.0 and -180.0 <= n_lng <= 180.0:
            out.append(encode(n_lat, n_lng, precision=p))
    return out


__all__ = ["decode_bbox", "encode", "neighbors"]
