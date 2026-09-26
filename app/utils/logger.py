# """
# logger.py

# Centralized logging configuration for Minddora AI.

# Provides:
#     configure_logging(app)  - Wires up rotating file handlers (for all
#                                routine DEBUG/INFO/WARNING/ERROR logs) plus
#                                a custom handler that persists WARNING-and-
#                                above events into the PostgreSQL-backed
#                                SystemLog table (app/models/log.py) so the
#                                Admin Panel's "Error Logs" page can query
#                                them without parsing log files.

#     log_to_db(...)           - Helper used directly by services/blueprints
#                                to write a structured event straight into
#                                SystemLog (e.g. failed login attempts,
#                                admin actions, RAG pipeline failures),
#                                independent of the standard logging module.

# Two logging destinations are intentionally kept separate:
#     1. Rotating file logs (storage/logs/minddora.log) — full-fidelity,
#        high-volume, cheap to write, used for debugging/tracing.
#     2. PostgreSQL SystemLog table — lower-volume, queryable/filterable,
#        used for the Admin Panel UI and long-term audit history.
# """

# import logging
# import os
# from logging.handlers import RotatingFileHandler

# from flask import Flask, request, has_request_context


# class RequestContextFilter(logging.Filter):
#     """
#     Injects request-specific context (IP address, request path) into every
#     log record when a Flask request context is active, so file logs include
#     that information without every call site having to pass it manually.
#     """

#     def filter(self, record: logging.LogRecord) -> bool:
#         if has_request_context():
#             record.ip_address = request.remote_addr
#             record.request_path = request.path
#         else:
#             record.ip_address = "N/A"
#             record.request_path = "N/A"
#         return True


# def configure_logging(app: Flask) -> None:
#     """
#     Configures Flask's built-in logger (app.logger) with:
#         - A rotating file handler writing to storage/logs/minddora.log
#         - A console (stream) handler for development visibility
#         - A request-context filter for IP/path enrichment

#     Args:
#         app: The Flask application instance being configured.
#     """

#     log_folder = app.config["LOG_FOLDER"]
#     os.makedirs(log_folder, exist_ok=True)
#     log_file_path = os.path.join(log_folder, "minddora.log")

#     log_format = logging.Formatter(
#         "[%(asctime)s] %(levelname)s in %(module)s "
#         "(ip=%(ip_address)s path=%(request_path)s): %(message)s"
#     )

#     # -----------------------------------------------------------------
#     # Rotating file handler — caps individual log files at 5 MB, keeps
#     # the last 10 rotated files (50 MB total ceiling) to avoid unbounded
#     # disk growth on the server.
#     # -----------------------------------------------------------------
#     file_handler = RotatingFileHandler(
#         log_file_path, maxBytes=5 * 1024 * 1024, backupCount=10
#     )
#     file_handler.setFormatter(log_format)
#     file_handler.addFilter(RequestContextFilter())
#     file_handler.setLevel(getattr(logging, app.config.get("LOG_LEVEL", "INFO")))

#     # -----------------------------------------------------------------
#     # Console handler — only verbose in development/debug mode.
#     # -----------------------------------------------------------------
#     console_handler = logging.StreamHandler()
#     console_handler.setFormatter(log_format)
#     console_handler.addFilter(RequestContextFilter())
#     console_handler.setLevel(logging.DEBUG if app.debug else logging.WARNING)

#     app.logger.addHandler(file_handler)
#     app.logger.addHandler(console_handler)
#     app.logger.setLevel(getattr(logging, app.config.get("LOG_LEVEL", "INFO")))

#     app.logger.info("Minddora AI logging configured successfully.")


# def log_to_db(
#     level: str,
#     category: str,
#     message: str,
#     context: dict = None,
#     user_id: int = None,
#     admin_id: int = None,
# ) -> None:
#     """
#     Persists a structured log event directly into the PostgreSQL
#     "system_logs" table via the SystemLog model. Intended for
#     significant events that admins need to search/filter in the UI —
#     NOT for high-volume debug tracing (use app.logger for that instead).

#     Args:
#         level: One of "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL".
#         category: One of "auth", "upload", "rag_pipeline", "chat",
#             "admin_action", "security", "database", "system".
#         message: Human-readable description of the event.
#         context: Optional dict of structured extra data (stored as JSONB).
#         user_id: Optional ID of the student user associated with the event.
#         admin_id: Optional ID of the admin associated with the event.

#     Note:
#         Imports are performed locally (inside the function) to avoid a
#         circular import between app/utils/logger.py, app/extensions.py,
#         and app/models/log.py, since logger.py is imported very early
#         during app/__init__.py's create_app() execution.
#     """
#     from flask import request, has_request_context

#     from app.extensions import db
#     from app.models.log import SystemLog

#     try:
#         entry = SystemLog(
#             level=level.upper(),
#             category=category,
#             message=message,
#             context=context,
#             user_id=user_id,
#             admin_id=admin_id,
#             ip_address=request.remote_addr if has_request_context() else None,
#             request_path=request.path if has_request_context() else None,
#         )
#         db.session.add(entry)
#         db.session.commit()
#         try:
#         entry = SystemLog(
#             level=level.upper(),
#             category=category,
#             message=message,
#             context=context,
#             user_id=user_id,
#             admin_id=admin_id,
#             ip_address=request.remote_addr if has_request_context() else None,
#             request_path=request.path if has_request_context() else None,
#         )
#         db.session.add(entry)
#         db.session.commit()

#         if category in ("auth", "upload", "admin_action"):
#             print(f"\n>>> [{category.upper()}] {message}\n")

#     # except Exception as exc:
#     except Exception as exc:  # noqa: BLE001 — logging must never crash the request
#         db.session.rollback()
#         # Fall back to file logging only, since the DB write itself failed.
#         logging.getLogger(__name__).error(
#             "Failed to write SystemLog entry to PostgreSQL: %s", exc
#         )


"""
logger.py

Centralized logging configuration for Minddora AI.

Provides:
    configure_logging(app)  - Wires up rotating file handlers (for all
                               routine DEBUG/INFO/WARNING/ERROR logs) plus
                               a custom handler that persists WARNING-and-
                               above events into the PostgreSQL-backed
                               SystemLog table (app/models/log.py) so the
                               Admin Panel's "Error Logs" page can query
                               them without parsing log files.

    log_to_db(...)           - Helper used directly by services/blueprints
                               to write a structured event straight into
                               SystemLog (e.g. failed login attempts,
                               admin actions, RAG pipeline failures),
                               independent of the standard logging module.

Two logging destinations are intentionally kept separate:
    1. Rotating file logs (storage/logs/minddora.log) — full-fidelity,
       high-volume, cheap to write, used for debugging/tracing.
    2. PostgreSQL SystemLog table — lower-volume, queryable/filterable,
       used for the Admin Panel UI and long-term audit history.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, request, has_request_context


class RequestContextFilter(logging.Filter):
    """
    Injects request-specific context (IP address, request path) into every
    log record when a Flask request context is active, so file logs include
    that information without every call site having to pass it manually.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            record.ip_address = request.remote_addr
            record.request_path = request.path
        else:
            record.ip_address = "N/A"
            record.request_path = "N/A"
        return True


def configure_logging(app: Flask) -> None:
    """
    Configures Flask's built-in logger (app.logger) with:
        - A rotating file handler writing to storage/logs/minddora.log
        - A console (stream) handler for development visibility
        - A request-context filter for IP/path enrichment

    Args:
        app: The Flask application instance being configured.
    """

    log_folder = app.config["LOG_FOLDER"]
    os.makedirs(log_folder, exist_ok=True)
    log_file_path = os.path.join(log_folder, "minddora.log")

    log_format = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s "
        "(ip=%(ip_address)s path=%(request_path)s): %(message)s"
    )

    # -----------------------------------------------------------------
    # Rotating file handler — caps individual log files at 5 MB, keeps
    # the last 10 rotated files (50 MB total ceiling) to avoid unbounded
    # disk growth on the server.
    # -----------------------------------------------------------------
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=10
    )
    file_handler.setFormatter(log_format)
    file_handler.addFilter(RequestContextFilter())
    file_handler.setLevel(getattr(logging, app.config.get("LOG_LEVEL", "INFO")))

    # -----------------------------------------------------------------
    # Console handler — only verbose in development/debug mode.
    # -----------------------------------------------------------------
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    console_handler.addFilter(RequestContextFilter())
    console_handler.setLevel(logging.DEBUG if app.debug else logging.WARNING)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(getattr(logging, app.config.get("LOG_LEVEL", "INFO")))

    app.logger.info("Minddora AI logging configured successfully.")


def log_to_db(
    level: str,
    category: str,
    message: str,
    context: dict = None,
    user_id: int = None,
    admin_id: int = None,
) -> None:
    """
    Persists a structured log event directly into the PostgreSQL
    "system_logs" table via the SystemLog model. Intended for
    significant events that admins need to search/filter in the UI —
    NOT for high-volume debug tracing (use app.logger for that instead).
    Also prints a clean, human-readable line to the console for key
    categories (auth, upload, admin_action) so login/logout/upload/
    delete events are immediately visible in the terminal, not just
    queryable later in the Admin Panel.

    Args:
        level: One of "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL".
        category: One of "auth", "upload", "rag_pipeline", "chat",
            "admin_action", "security", "database", "system".
        message: Human-readable description of the event.
        context: Optional dict of structured extra data (stored as JSONB).
        user_id: Optional ID of the student user associated with the event.
        admin_id: Optional ID of the admin associated with the event.

    Note:
        Imports are performed locally (inside the function) to avoid a
        circular import between app/utils/logger.py, app/extensions.py,
        and app/models/log.py, since logger.py is imported very early
        during app/__init__.py's create_app() execution.
    """
    from flask import request, has_request_context

    from app.extensions import db
    from app.models.log import SystemLog

    try:
        entry = SystemLog(
            level=level.upper(),
            category=category,
            message=message,
            context=context,
            user_id=user_id,
            admin_id=admin_id,
            ip_address=request.remote_addr if has_request_context() else None,
            request_path=request.path if has_request_context() else None,
        )
        db.session.add(entry)
        db.session.commit()

        if category in ("auth", "upload", "admin_action"):
            print(f"\n>>> [{category.upper()}] {message}\n")

    except Exception as exc:  # noqa: BLE001 — logging must never crash the request
        db.session.rollback()
        # Fall back to file logging only, since the DB write itself failed.
        logging.getLogger(__name__).error(
            "Failed to write SystemLog entry to PostgreSQL: %s", exc
        )