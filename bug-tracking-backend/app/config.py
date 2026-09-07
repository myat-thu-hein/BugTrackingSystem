"""
app/config.py
--------------
Loads all configuration and secrets from environment variables, and
creates the single shared Supabase client used by the whole app.

Nothing in this file should ever contain a hard-coded secret. Everything
comes from a .env file locally (loaded with python-dotenv) or from the
Render dashboard's Environment Variables in production.
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load variables from a local .env file if one exists.
# On Render, real environment variables are injected directly and this
# call is harmless (it just won't find a .env file).
load_dotenv()


class Config:
    # --- Supabase ---
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # service_role key (see README)

    # --- JWT ---
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRES_HOURS = int(os.environ.get("JWT_EXPIRES_HOURS", "24"))

    # --- CORS ---
    # Comma-separated list of allowed frontend origins, e.g.
    # "http://localhost:5173,https://my-frontend.vercel.app"
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    # --- Flask ---
    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = FLASK_ENV == "development"


def validate_config():
    """Fail fast and loudly if required secrets are missing."""
    missing = []
    for key in ("SUPABASE_URL", "SUPABASE_KEY", "JWT_SECRET_KEY"):
        if not getattr(Config, key):
            missing.append(key)
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill these in."
        )


def get_supabase_client() -> Client:
    """
    Creates a Supabase client using the SERVICE ROLE key.

    IMPORTANT: We use the service_role key (not the anon key) because the
    Flask backend does its own authentication/authorization with JWT and
    talks to the database directly on the user's behalf. The service_role
    key bypasses Supabase Row Level Security (RLS), which is fine here
    because our Flask app is the ONLY thing enforcing access control.

    This key must NEVER be sent to the frontend or exposed publicly -
    it lives only in this backend's environment variables.
    """
    validate_config()
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
