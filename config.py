import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def normalize_database_uri(value: str | None) -> str:
    if not value:
        return f"sqlite:///{BASE_DIR / 'diagnostico.db'}"
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://") and "+psycopg" not in value:
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "cambiar-antes-de-produccion")
    SQLALCHEMY_DATABASE_URI = normalize_database_uri(os.getenv("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "csv",
        "zip",
        "png",
        "jpg",
        "jpeg",
    }
    SESSION_COOKIE_SAMESITE = "Lax"
    BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    BOOTSTRAP_ADMIN_NAME = os.getenv("BOOTSTRAP_ADMIN_NAME", "Administrador Inicial")
    AUTO_INIT_DATABASE = os.getenv("AUTO_INIT_DATABASE", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Hermosillo")
