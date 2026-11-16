"""
app/__init__.py
-----------------
Flask application factory. `create_app()` loads config, enables CORS,
attaches the Supabase client, and registers every blueprint.

Arguments exist mainly for testing:
  config_overrides  - dict merged over Config (e.g. a test JWT secret)
  supabase_client   - inject a fake client instead of connecting to Supabase
"""

import logging

from flask import Flask
from flask_cors import CORS

from app.config import Config, create_supabase_client
from app.errors import register_error_handlers


def create_app(config_overrides=None, supabase_client=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    logging.basicConfig(
        level=app.config.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # One shared client for the whole app (see app/extensions.py::get_db).
    app.config["SUPABASE_CLIENT"] = supabase_client or create_supabase_client()

    # The API authenticates with a Bearer token header (not cookies), so
    # credentialed CORS is unnecessary - and "*" + credentials is unsafe.
    origins = app.config["CORS_ORIGINS"]
    origins = "*" if origins == "*" else [o.strip() for o in origins.split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=False)

    from app.routes.admin_requests import admin_requests_bp
    from app.routes.auth import auth_bp
    from app.routes.bugs import bugs_bp
    from app.routes.comments import comments_bp
    from app.routes.health import health_bp
    from app.routes.notifications import notifications_bp
    from app.routes.projects import projects_bp
    from app.routes.support import support_bp
    from app.routes.users import users_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(bugs_bp, url_prefix="/api/bugs")
    app.register_blueprint(comments_bp, url_prefix="/api/bugs")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(projects_bp, url_prefix="/api/projects")
    app.register_blueprint(admin_requests_bp, url_prefix="/api/admin-requests")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(support_bp, url_prefix="/api/support")
    app.register_blueprint(health_bp, url_prefix="/api/health")

    register_error_handlers(app)
    return app
