"""
analytics_service.py

Usage statistics aggregation layer, serving two distinct audiences:

    Student-facing ("AI Analytics" page): personal usage stats — how
        many documents uploaded, how many chat questions asked, storage
        used, most-active subjects, activity over time.

    Admin-facing ("System Analytics" page): platform-wide stats — total
        users, total documents, total chat messages, vector store size,
        signups over time, top error categories, storage usage across
        all users.

All aggregation queries run directly against PostgreSQL via SQLAlchemy,
using COUNT/SUM/GROUP BY rather than loading full row sets into Python,
to keep these dashboard queries fast even as usage grows.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.document import Document
from app.models.chat import ChatSession, ChatMessage
from app.models.feedback import Feedback
from app.models.log import SystemLog
from app.services import vector_store_service


# ---------------------------------------------------------------------------
# Student-Facing Analytics ("AI Analytics" page)
# ---------------------------------------------------------------------------
def get_student_analytics(user_id: int, days: int = 30) -> dict:
    """
    Aggregates personal usage statistics for a single student, powering
    the "AI Analytics" dashboard page.

    Args:
        user_id: The student's User.id.
        days: Number of trailing days to include in the activity-over-time
            breakdown.

    Returns:
        A dict containing:
            "total_documents": int
            "total_chunks": int
            "total_chat_sessions": int
            "total_questions_asked": int
            "storage_used_bytes": int
            "storage_quota_bytes": int
            "average_confidence_score": float
            "questions_per_day": list[{"date": str, "count": int}]
            "top_subjects": list[{"subject": str, "document_count": int}]
    """
    user = User.query.get(user_id)
    if user is None:
        return {}

    total_documents = Document.query.filter_by(user_id=user_id, is_deleted=False).count()
    total_chunks = db.session.query(func.sum(Document.total_chunks)).filter_by(
        user_id=user_id, is_deleted=False
    ).scalar() or 0
    total_chat_sessions = ChatSession.query.filter_by(user_id=user_id).count()

    total_questions_asked = (
        db.session.query(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id, ChatMessage.role == "user")
        .scalar()
        or 0
    )

    average_confidence = (
        db.session.query(func.avg(ChatMessage.confidence_score))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id, ChatMessage.role == "assistant")
        .scalar()
    )

    return {
        "total_documents": total_documents,
        "total_chunks": int(total_chunks),
        "total_chat_sessions": total_chat_sessions,
        "total_questions_asked": total_questions_asked,
        "storage_used_bytes": user.storage_used_bytes,
        "storage_quota_bytes": user.storage_quota_bytes,
        "average_confidence_score": round(float(average_confidence), 4) if average_confidence else 0.0,
        "questions_per_day": _questions_per_day(user_id, days),
        "top_subjects": _top_subjects_for_user(user_id),
    }


def _questions_per_day(user_id: int, days: int) -> list:
    """
    Builds a day-by-day count of questions asked over the trailing
    `days` window, used to render an activity chart on the AI Analytics page.

    Args:
        user_id: The student's User.id.
        days: Number of trailing days to include.

    Returns:
        A list of {"date": "YYYY-MM-DD", "count": int} dicts, ordered
        oldest to newest, including days with zero activity.
    """
    since_date = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.session.query(
            func.date(ChatMessage.created_at).label("day"),
            func.count(ChatMessage.id).label("count"),
        )
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(
            ChatSession.user_id == user_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= since_date,
        )
        .group_by(func.date(ChatMessage.created_at))
        .all()
    )

    counts_by_day = {row.day.isoformat(): row.count for row in rows}

    result = []
    for i in range(days, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        result.append({"date": day, "count": counts_by_day.get(day, 0)})

    return result


def _top_subjects_for_user(user_id: int, limit: int = 5) -> list:
    """
    Returns the student's most-used document subjects/categories, ranked
    by document count, used for a "top subjects" chart on the AI
    Analytics page.

    Args:
        user_id: The student's User.id.
        limit: Maximum number of subjects to return.

    Returns:
        A list of {"subject": str, "document_count": int} dicts.
    """
    rows = (
        db.session.query(Document.subject, func.count(Document.id).label("document_count"))
        .filter(Document.user_id == user_id, Document.is_deleted.is_(False), Document.subject.isnot(None))
        .group_by(Document.subject)
        .order_by(func.count(Document.id).desc())
        .limit(limit)
        .all()
    )
    return [{"subject": row.subject, "document_count": row.document_count} for row in rows]


# ---------------------------------------------------------------------------
# Admin-Facing Analytics ("System Analytics" page)
# ---------------------------------------------------------------------------
def get_system_analytics(days: int = 30) -> dict:
    """
    Aggregates platform-wide usage statistics for the Admin Panel's
    System Analytics page.

    Args:
        days: Number of trailing days to include in the signups-over-time
            and questions-over-time breakdowns.

    Returns:
        A dict containing:
            "total_users": int
            "active_users": int
            "total_documents": int
            "total_chunks": int
            "total_chat_sessions": int
            "total_questions_asked": int
            "total_vectors_stored": int
            "total_storage_used_bytes": int
            "signups_per_day": list[{"date": str, "count": int}]
            "questions_per_day": list[{"date": str, "count": int}]
            "open_feedback_count": int
            "error_log_count_last_24h": int
    """
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    total_documents = Document.query.filter_by(is_deleted=False).count()
    total_chunks = db.session.query(func.sum(Document.total_chunks)).filter_by(is_deleted=False).scalar() or 0
    total_chat_sessions = ChatSession.query.count()
    total_questions_asked = ChatMessage.query.filter_by(role="user").count()
    total_storage_used = db.session.query(func.sum(User.storage_used_bytes)).scalar() or 0

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    error_log_count = SystemLog.query.filter(
        SystemLog.level.in_(["ERROR", "CRITICAL"]), SystemLog.created_at >= since_24h
    ).count()

    open_feedback_count = Feedback.query.filter_by(status="open").count()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_documents": total_documents,
        "total_chunks": int(total_chunks),
        "total_chat_sessions": total_chat_sessions,
        "total_questions_asked": total_questions_asked,
        "total_vectors_stored": vector_store_service.get_total_vector_count(),
        "total_storage_used_bytes": int(total_storage_used),
        "signups_per_day": _signups_per_day(days),
        "questions_per_day": _system_questions_per_day(days),
        "open_feedback_count": open_feedback_count,
        "error_log_count_last_24h": error_log_count,
    }


def _signups_per_day(days: int) -> list:
    """
    Builds a day-by-day count of new user registrations over the
    trailing `days` window, used for a growth chart on the System
    Analytics page.

    Args:
        days: Number of trailing days to include.

    Returns:
        A list of {"date": "YYYY-MM-DD", "count": int} dicts, ordered
        oldest to newest, including days with zero signups.
    """
    since_date = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.session.query(func.date(User.created_at).label("day"), func.count(User.id).label("count"))
        .filter(User.created_at >= since_date)
        .group_by(func.date(User.created_at))
        .all()
    )

    counts_by_day = {row.day.isoformat(): row.count for row in rows}

    result = []
    for i in range(days, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        result.append({"date": day, "count": counts_by_day.get(day, 0)})

    return result


def _system_questions_per_day(days: int) -> list:
    """
    Builds a day-by-day count of questions asked platform-wide over the
    trailing `days` window, used for an activity chart on the System
    Analytics page.

    Args:
        days: Number of trailing days to include.

    Returns:
        A list of {"date": "YYYY-MM-DD", "count": int} dicts, ordered
        oldest to newest, including days with zero activity.
    """
    since_date = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.session.query(func.date(ChatMessage.created_at).label("day"), func.count(ChatMessage.id).label("count"))
        .filter(ChatMessage.role == "user", ChatMessage.created_at >= since_date)
        .group_by(func.date(ChatMessage.created_at))
        .all()
    )

    counts_by_day = {row.day.isoformat(): row.count for row in rows}

    result = []
    for i in range(days, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        result.append({"date": day, "count": counts_by_day.get(day, 0)})

    return result