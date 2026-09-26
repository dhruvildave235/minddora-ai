"""
run.py

Application entry point for Minddora AI.

This script:
    1. Loads environment variables from the .env file (via python-dotenv).
    2. Creates the Flask application instance using the application factory.
    3. Runs the development server when executed directly (e.g. `python run.py`).

In production, this file is NOT used to start the server directly. Instead,
a WSGI server such as Gunicorn imports the `app` object from this module,
e.g.:

    gunicorn -w 4 -b 0.0.0.0:8000 run:app

Environment variables (including PostgreSQL connection details) are read
from the ".env" file at the project root, based on ".env.example".
"""

import os

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load environment variables from .env BEFORE importing app/config.py,
# so that PostgreSQL credentials (DB_USER, DB_PASSWORD, DATABASE_URL, etc.)
# and all other settings are available when create_app() builds the config.
# ---------------------------------------------------------------------------
load_dotenv()

from app import create_app  # noqa: E402  (import after load_dotenv intentionally)

# ---------------------------------------------------------------------------
# Create the Flask app using the factory, selecting the environment from
# FLASK_ENV (defaults to "development" inside create_app if unset).
# ---------------------------------------------------------------------------
app = create_app(os.environ.get("FLASK_ENV", "development"))

print(f">>> Loaded config: {app.config.get('RATELIMIT_DEFAULT')} | SESSION_COOKIE_SECURE={app.config.get('SESSION_COOKIE_SECURE')}")


if __name__ == "__main__":
    # -----------------------------------------------------------------
    # Local development server only.
    # host="0.0.0.0" allows access from other devices on the same network
    # (e.g. testing the responsive UI on a phone/tablet).
    # debug is driven by app.config["DEBUG"], set via DevelopmentConfig.
    # -----------------------------------------------------------------
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config.get("DEBUG", False),
    )

   