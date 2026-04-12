"""Flask application factory for Quorum."""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, render_template

from config import get_config
from .extensions import csrf, db, login_manager, migrate


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=False,
        template_folder="templates",
        static_folder="static",
    )

    config_cls = get_config(config_name)
    app.config.from_object(config_cls)

    # Ensure instance/upload directories exist.
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    instance_dir = Path(app.root_path).parent / "instance"
    instance_dir.mkdir(parents=True, exist_ok=True)

    # Init extensions.
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register models so Flask-Migrate sees them.
    from . import models  # noqa: F401

    @login_manager.user_loader
    def _load_user(user_id: str):
        return db.session.get(models.User, int(user_id))

    # Register blueprints.
    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .users import bp as users_bp
    from .meetings import bp as meetings_bp
    from .meetings.live_routes import bp as live_bp
    from .agendas import bp as agendas_bp
    from .minutes import bp as minutes_bp
    from .reports import bp as reports_bp
    from .attachments import bp as attachments_bp
    from .boards import bp as boards_bp
    from .kiosk import bp as kiosk_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(live_bp)
    app.register_blueprint(agendas_bp)
    app.register_blueprint(minutes_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(attachments_bp)
    app.register_blueprint(boards_bp)
    app.register_blueprint(kiosk_bp)

    # Register CLI commands.
    from . import cli
    cli.register(app)

    # Error handlers.
    @app.errorhandler(403)
    def _forbidden(_err):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def _not_found(_err):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def _server_error(_err):
        return render_template("errors/500.html"), 500

    # Template globals.
    from .rro import STAGE_LABELS, MOTION_TYPE_LABELS
    from .permissions import CHAIR_ROLES, SECRETARY_ROLES

    @app.context_processor
    def _inject_globals():
        return {
            "app_name": "Quorum",
            "church_display_name": app.config.get(
                "CHURCH_DISPLAY_NAME", "Connection Church"
            ),
            "church_legal_name": app.config.get(
                "CHURCH_LEGAL_NAME", "Tri-City Assembly of God"
            ),
            "parliamentary_authority": app.config.get(
                "PARLIAMENTARY_AUTHORITY",
                "Robert's Rules of Order Newly Revised",
            ),
            "stage_labels": STAGE_LABELS,
            "motion_type_labels": MOTION_TYPE_LABELS,
            "chair_roles": CHAIR_ROLES,
            "secretary_roles": SECRETARY_ROLES,
        }

    return app
