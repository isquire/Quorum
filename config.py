"""Configuration classes for the Quorum application."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", str(BASE_DIR / "uploads")
    )
    MAX_CONTENT_LENGTH = int(
        os.environ.get("MAX_CONTENT_LENGTH", 25 * 1024 * 1024)
    )
    ALLOWED_UPLOAD_EXTENSIONS = {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "txt", "md", "png", "jpg", "jpeg", "gif", "csv",
    }

    WTF_CSRF_ENABLED = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    TIMEZONE = os.environ.get("TIMEZONE", "America/Chicago")

    # Quorum rule: majority of voting members (ceil(n/2) + 1 or
    # traditional "simple majority"); we use floor(n/2) + 1.
    QUORUM_FRACTION = 0.5  # strictly more than half


class DevConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'quorum.db'}"
    )


class ProdConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:////app/instance/quorum.db"
    )


class TestConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"


CONFIGS = {
    "dev": DevConfig,
    "prod": ProdConfig,
    "testing": TestConfig,
}


def get_config(name: str | None = None):
    name = name or os.environ.get("FLASK_CONFIG", "prod")
    return CONFIGS.get(name, ProdConfig)
