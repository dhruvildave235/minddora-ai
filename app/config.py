"""
config.py

Centralized, environment-based configuration for the Minddora AI application.
Reads all sensitive/environment-specific values from environment variables
(loaded via python-dotenv in run.py) and never hardcodes secrets.

Classes:
    Config            - Base configuration shared by all environments.
    DevelopmentConfig - Local development overrides.
    TestingConfig      - Configuration used by the automated test suite.
    ProductionConfig   - Production-hardened configuration.

Usage:
    from app.config import config_by_name
    app.config.from_object(config_by_name[os.getenv("FLASK_ENV", "development")])
"""

import os
from datetime import timedelta

# Absolute path to the project root directory (two levels up from this file)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config:
    """
    Base configuration class.

    Holds settings that are common across every environment. Environment-specific
    subclasses override only the values that need to differ.
    """

    # ---------------------------------------------------------------------
    # Core Flask Settings
    # ---------------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-env-file")
    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = False

    # ---------------------------------------------------------------------
    # Database Settings — PostgreSQL
    # ---------------------------------------------------------------------
    DB_USER = os.environ.get("DB_USER", "minddora_user")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "pass pls")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "minddora_db")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,   # Verifies connections before use (handles dropped conns)
        "pool_recycle": 280,     # Recycle connections before Postgres/idle timeout
        "pool_size": 10,
        "max_overflow": 20,
    }

    # ---------------------------------------------------------------------
    # Session / Auth Settings
    # ---------------------------------------------------------------------
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=14)

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-this-jwt-secret-in-env-file")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=6)


    # ---------------------------------------------------------------------
    # Mail Configuration
    # ---------------------------------------------------------------------
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True").lower() == "true"
    AIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "False").lower() == "true"

    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")


    # ---------------------------------------------------------------------
    # Database Browser Panel — separate secret from admin login password,
    # required to unlock the Admin Panel's raw Database tab.
    # ---------------------------------------------------------------------
    DB_PANEL_PASSWORD = os.environ.get("DB_PANEL_PASSWORD", "change-this-in-env")

    # ---------------------------------------------------------------------
    # File Upload Settings
    # ---------------------------------------------------------------------
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "storage", "uploads")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB per upload request
    ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md", "png", "jpg", "jpeg"}

    # ---------------------------------------------------------------------
    # Vector Database Settings
    # ---------------------------------------------------------------------
    VECTOR_DB_PROVIDER = os.environ.get("VECTOR_DB_PROVIDER", "faiss")  # "faiss" or "chromadb"
    VECTOR_DB_PATH = os.path.join(BASE_DIR, "storage", "vector_db")
    EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    EMBEDDING_DIMENSION = 384  # Output dimension of all-MiniLM-L6-v2

    # ---------------------------------------------------------------------
    # RAG / Chunking Settings
    # ---------------------------------------------------------------------
    CHUNK_SIZE = 350         # Target tokens per chunk
    CHUNK_OVERLAP = 150       # Overlap tokens between consecutive chunks
    TOP_K_RETRIEVAL = 1       # Number of chunks retrieved per query 5,3
    SIMILARITY_THRESHOLD = 0.08  # Minimum relevance score to include a chunk 0.35

    # ---------------------------------------------------------------------
    # Logging
    # ---------------------------------------------------------------------
    LOG_FOLDER = os.path.join(BASE_DIR, "storage", "logs")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    # ---------------------------------------------------------------------
    # Rate Limiting
    # ---------------------------------------------------------------------
    # RATELIMIT_DEFAULT = "2000 per day, 500 per hour"
    RATELIMIT_DEFAULT = "50000 per day, 20000 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class DevelopmentConfig(Config):
    """Configuration used during local development."""

    DEBUG = True
    SQLALCHEMY_ECHO = False
  
    RATELIMIT_DEFAULT = "50000 per day, 20000 per hour"
    SEND_FILE_MAX_AGE_DEFAULT = 0
    
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    
class TestingConfig(Config):
    """Configuration used by the automated pytest suite."""

    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://minddora_user:pass pls@localhost:5432/minddora_test_db",
    )
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production-hardened configuration."""

    DEBUG = False
    SQLALCHEMY_ECHO = False
    SESSION_COOKIE_SECURE = True  # Requires HTTPS
    PREFERRED_URL_SCHEME = "https"


# ---------------------------------------------------------------------------
# Config Registry — selected in app/__init__.py via FLASK_ENV
# ---------------------------------------------------------------------------
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

