"""
Alembic Autogenerate İçin Tüm Modellerin Toplandığı Modül
========================================================
Alembic'in ``target_metadata`` parametresine ``Base.metadata`` verirken,
modellerin import edilmiş olması gerekir. Bu dosya yalnızca import zincirini
tetiklemek için vardır.
"""

from app.db.base_class import Base  # noqa: F401

# --- Tüm modeller buradan import edilir (Alembic için kritik) ---------------
from app.models import (  # noqa: F401
    AIDecisionLog,
    AIDecisionQueue,
    AuditLog,
    ETLRunLog,
    Favorite,
    Follow,
    MergeDecisionLog,
    OpeningHours,
    Photo,
    Place,
    PlaceTag,
    RefreshToken,
    Report,
    Review,
    Route,
    RouteComment,
    RouteLike,
    RouteStop,
    Tag,
    User,
)
