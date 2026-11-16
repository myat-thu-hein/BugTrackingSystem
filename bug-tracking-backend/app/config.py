"""
app/config.py
--------------
Loads all configuration from environment variables and builds the shared
Supabase client. Nothing here contains a hard-coded secret: values come
from a local .env file (python-dotenv) or the Render dashboard.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = ("SUPABASE_URL", "SUPABASE_KEY", "JWT_SECRET_KEY")
MIN_JWT_SECRET_LENGTH = 32


class Config:
    # --- Supabase ---
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # service_role key (see README)

    # --- JWT ---
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRES_HOURS = int(os.environ.get("JWT_EXPIRES_HOURS", "24"))

    # --- CORS --- comma-separated origins, or "*" for any origin
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    # --- Requests --- JSON bodies here are tiny; reject anything huge (413).
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(1024 * 1024)))

    # --- Platform owners --- comma-separated emails. Registering with one of
    # these makes the account an "owner": owners approve admin requests and
    # receive the request emails. Owners don't belong to a project.
    OWNER_EMAILS = os.environ.get("OWNER_EMAILS", "")

    # --- Email (optional) --- any SMTP account works (Gmail app password,
    # Brevo, Mailtrap...). Without SMTP_HOST, emails are written to the log
    # instead, so the app runs fine with no email setup.
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"  # true for port 465
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "")  # defaults to SMTP_USER
    # Public URL of the frontend, used for links inside emails.
    APP_URL = os.environ.get("APP_URL", "http://localhost:5173").rstrip("/")

    # --- Flask ---
    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = FLASK_ENV == "development"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def validate_config(config=Config):
    """Fail fast and loudly if required secrets are missing."""
    missing = [key for key in REQUIRED_SETTINGS if not getattr(config, key, None)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill these in."
        )
    if len(config.JWT_SECRET_KEY) < MIN_JWT_SECRET_LENGTH:
        logger.warning(
            "JWT_SECRET_KEY is shorter than %d characters; use a longer random value.",
            MIN_JWT_SECRET_LENGTH,
        )


def create_supabase_client(config=Config):
    """
    Create a Supabase client using the SERVICE ROLE key.

    The Flask backend does its own authentication/authorization (JWT + role
    checks), so it needs the service_role key, which bypasses Row Level
    Security. This key must NEVER reach the frontend or version control.

    The `supabase` import is local so unit tests (which inject a fake client)
    don't need the package installed.
    """
    from supabase import create_client

    from app.services.supabase_http import use_http1_for_postgrest

    validate_config(config)
    # One shared HTTP/2 connection breaks under parallel requests (WinError
    # 10035 on Windows); HTTP/1.1 gives each request its own connection.
    use_http1_for_postgrest()
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
