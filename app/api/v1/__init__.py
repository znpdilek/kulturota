"""
v1 API Aggregator
=================
Tüm v1 router'larını tek bir :class:`fastapi.APIRouter` altında toplar.
"""

from fastapi import APIRouter

from app.api.v1 import auth as auth_router
from app.api.v1 import photos as photos_router
from app.api.v1 import places as places_router
from app.api.v1 import reviews as reviews_router
from app.api.v1 import route_likes as route_likes_router
from app.api.v1 import routes as routes_router
from app.api.v1 import users as users_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth_router.router)
# Adım 4 ile gelen GET /v1/me — backward compat için tutuluyor.
api_router.include_router(users_router.legacy_router)
# Adım 5: GET/PUT/DELETE /v1/users/me ailesi + /v1/users/me/export-data.
api_router.include_router(users_router.router)
api_router.include_router(places_router.router)
# Adım 6: POST /v1/photos (multipart) — S3/MinIO + EXIF temizleme + DB.
api_router.include_router(photos_router.router)
# GET /v1/places/{id}/photos — public foto galerisi.
api_router.include_router(photos_router.places_photos_router)
# Adım 7: /v1/routes + /v1/routes/{id}/stops — rota CRUD ve stop yönetimi.
api_router.include_router(routes_router.router)
# Adım 8: Sosyal MVP — /v1/places/{id}/reviews (yorum) +
# /v1/routes/{id}/likes (beğeni). Takip / nested comment / bildirim
# altyapısı kapsam dışıdır (kullanıcı talebi).
api_router.include_router(reviews_router.router)
api_router.include_router(route_likes_router.router)

__all__ = ["api_router"]
