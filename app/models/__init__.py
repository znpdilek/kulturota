"""
SQLAlchemy ORM Modelleri
========================
PRD v2.0 — Bölüm 10 (Veritabanı Tasarımı) ve Bölüm 11 (ERD) referans alınmıştır.
"""

from app.models.ai_decision_log import AIDecisionLog
from app.models.ai_decision_queue import AIDecisionQueue
from app.models.audit_log import AuditLog
from app.models.etl_run_log import ETLRunLog
from app.models.favorite import Favorite
from app.models.follow import Follow
from app.models.merge_decision_log import MergeDecisionLog
from app.models.opening_hours import OpeningHours
from app.models.photo import Photo
from app.models.place import Place
from app.models.place_tag import PlaceTag
from app.models.refresh_token import RefreshToken
from app.models.report import Report
from app.models.review import Review
from app.models.route import Route
from app.models.route_comment import RouteComment
from app.models.route_like import RouteLike
from app.models.route_stop import RouteStop
from app.models.tag import Tag
from app.models.user import User

__all__ = [
    "AIDecisionLog",
    "AIDecisionQueue",
    "AuditLog",
    "ETLRunLog",
    "Favorite",
    "Follow",
    "MergeDecisionLog",
    "OpeningHours",
    "Photo",
    "Place",
    "PlaceTag",
    "RefreshToken",
    "Report",
    "Review",
    "Route",
    "RouteComment",
    "RouteLike",
    "RouteStop",
    "Tag",
    "User",
]
