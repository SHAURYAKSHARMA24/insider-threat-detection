"""Flask application factory for the Insider Threat Detection System.

Creates the configured Flask app, registers the SQLite data layer, exposes a
lightweight ``/health`` route, and registers the dashboard/API blueprint.
"""
from flask import Flask, jsonify

from .config import Config


def create_app(config_class=Config):
    """Create and configure the Flask application.

    Args:
        config_class: configuration object to load (defaults to ``Config``).

    Returns:
        A configured :class:`flask.Flask` application instance.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register the SQLite data layer (request-scoped connection teardown).
    from . import db

    db.init_app(app)

    @app.route("/health")
    def health():
        """Lightweight liveness check used by tests and the live demo."""
        return jsonify(status="ok"), 200

    # Register the backend API routes (dashboard data + filters).
    from . import routes

    app.register_blueprint(routes.bp)

    return app
