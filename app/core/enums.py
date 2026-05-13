"""
Uygulama Genelinde Kullanılan Enum'lar
======================================
PRD Bölüm 10'da geçen tüm enum tipleri burada toplanır. Modeller bu enum'ları
SQLAlchemy ``Enum(... name="...")`` ile native PostgreSQL ``ENUM`` tipine map'ler.
"""

from __future__ import annotations

import enum


# --- USERS -------------------------------------------------------------------
class UserRole(str, enum.Enum):
    """
    PRD 10.2 + 17.2: küratör rolleri D6 ile kaldırılmıştır.
    """

    USER = "user"
    ADMIN = "admin"


# --- AUTH (PRD §12.1 + §17.2) ------------------------------------------------
class TokenType(str, enum.Enum):
    """JWT ``typ`` claim'i — access ve refresh token'lar ayrı doğrulanır."""

    ACCESS = "access"
    REFRESH = "refresh"


# --- ROUTES ------------------------------------------------------------------
class RouteDifficulty(str, enum.Enum):
    """PRD 10.2 routes.difficulty (enum)."""

    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


# --- AI DECISION QUEUE -------------------------------------------------------
class AIDecisionReason(str, enum.Enum):
    """PRD 10.2 ai_decision_queue.reason."""

    LOW_CONFIDENCE = "low_confidence"
    MISSING_FIELD = "missing_field"
    CONFLICT = "conflict"
    GEOFENCE = "geofence"


class AIDecisionStatus(str, enum.Enum):
    """PRD 10.2 ai_decision_queue.status."""

    PENDING = "pending"
    PROCESSED = "processed"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    RETRY = "retry"


# --- AI DECISION LOG ---------------------------------------------------------
class AIModelProvider(str, enum.Enum):
    """PRD 9.2 + 10.2 ai_decision_log.model_provider."""

    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    MISTRAL = "mistral"


class AIDecisionType(str, enum.Enum):
    """PRD 9.4 + 10.2 ai_decision_log.decision."""

    MERGE = "merge"
    SPLIT = "split"
    REJECT = "reject"


# --- REPORTS (polimorfik) ----------------------------------------------------
class ReportTargetType(str, enum.Enum):
    """PRD 10.2 + 11.1 reports.target_type — polimorfik referans."""

    PLACE = "place"
    PHOTO = "photo"
    REVIEW = "review"
    ROUTE = "route"
    USER = "user"


class ReportStatus(str, enum.Enum):
    """PRD 10.2 reports.status."""

    AUTO_RESOLVED = "auto_resolved"
    ESCALATED = "escalated"
    DISMISSED = "dismissed"


class ReportAutoAction(str, enum.Enum):
    """PRD 10.2 reports.auto_action."""

    HIDDEN = "hidden"
    NONE = "none"


# --- OPENING HOURS -----------------------------------------------------------
class OpeningHoursSource(str, enum.Enum):
    """PRD 10.2 opening_hours.source."""

    BIZIZMIR = "bizizmir"
    OSM = "osm"
    LLM = "llm"
    SCRAPE = "scrape"
