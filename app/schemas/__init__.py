"""Pydantic şemaları — request/response DTO'ları (PRD §12)."""

from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.photo import PhotoUploadProblem, PhotoUploadResponse
from app.schemas.place import (
    AttributionItem,
    Coordinate,
    NearbyListResponse,
    NearbyPlace,
    PlaceDetail,
    PlaceListMeta,
    PlaceListResponse,
    PlaceSummary,
)
from app.schemas.review import (
    ReviewAggregate,
    ReviewCreate,
    ReviewListResponse,
    ReviewResponse,
)
from app.schemas.route import (
    PlaceMini,
    RouteCreate,
    RouteDetail,
    RouteListResponse,
    RouteStopCreate,
    RouteStopListResponse,
    RouteStopUpdate,
    RouteStopWithPlace,
    RouteSummary,
    RouteUpdate,
)
from app.schemas.route_like import RouteLikeResponse, RouteLikeStatus
from app.schemas.user import UserMe, UserPublic

__all__ = [
    "AttributionItem",
    "Coordinate",
    "LoginRequest",
    "LogoutRequest",
    "NearbyListResponse",
    "NearbyPlace",
    "PhotoUploadProblem",
    "PhotoUploadResponse",
    "PlaceDetail",
    "PlaceListMeta",
    "PlaceListResponse",
    "PlaceMini",
    "PlaceSummary",
    "RefreshRequest",
    "RegisterRequest",
    "ReviewAggregate",
    "ReviewCreate",
    "ReviewListResponse",
    "ReviewResponse",
    "RouteCreate",
    "RouteDetail",
    "RouteLikeResponse",
    "RouteLikeStatus",
    "RouteListResponse",
    "RouteStopCreate",
    "RouteStopListResponse",
    "RouteStopUpdate",
    "RouteStopWithPlace",
    "RouteSummary",
    "RouteUpdate",
    "TokenPair",
    "UserMe",
    "UserPublic",
]
