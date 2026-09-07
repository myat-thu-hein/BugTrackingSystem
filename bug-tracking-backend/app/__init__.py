"""
app/__init__.py
-----------------
The Flask "application factory". `create_app()` builds and configures the
Flask app: it loads config, sets up CORS, creates the Supabase client, and
registers every blueprint (route module).

run.py imports create_app() and actually starts the server.
"""

from flask import Flask
from flask_cors import CORS

from app.config import Config, get_supabase_client
from app.utils.responses import error_response


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Create ONE shared Supabase client and stash it on app.config so every
    # route/middleware module can reach it via current_app.config["SUPABASE_CLIENT"]
    # instead of creating a new client per request.
    app.config["SUPABASE_CLIENT"] = get_supabase_client()

    # --- CORS ---
    # Allows the frontend (a different origin) to call this API from the browser.
    origins = Config.CORS_ORIGINS
    origins = origins.split(",") if origins != "*" else "*"
    CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)

    # --- Blueprints ---
    from app.routes.auth import auth_bp
    from app.routes.bugs import bugs_bp
    from app.routes.comments import comments_bp
    from app.routes.users import users_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(bugs_bp, url_prefix="/api/bugs")
    app.register_blueprint(comments_bp, url_prefix="/api/bugs")
    app.register_blueprint(users_bp, url_prefix="/api/users")

    # --- Health check (useful for Render + quick sanity testing) ---
    @app.route("/api/health")
    def health():
        return {"success": True, "message": "Bug Tracking API is running"}

    # --- Global error handlers so unexpected errors still return clean JSON ---
    @app.errorhandler(404)
    def not_found(e):
        return error_response("Resource not found", 404)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return error_response("Method not allowed on this endpoint", 405)

    @app.errorhandler(500)
    def server_error(e):
        return error_response("Internal server error", 500)

    return app
