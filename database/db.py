"""
database/db.py
--------------
SQLAlchemy + Flask-SQLAlchemy setup for Spendly.

URL priority:
  1. DATABASE_URL_POOLED  (pooled Neon connection — used by the running app)
  2. DATABASE_URL          (direct Neon connection — fallback)
  3. sqlite:///local.db    (last-resort local dev fallback)

Both "postgres://" and "postgresql://" schemes are accepted; the former is
silently normalised to the latter so SQLAlchemy does not reject it.

pool_pre_ping=True is set so Neon's idle-connection drops do not break
in-flight requests.

NOTE: db.create_all() is intentionally absent — schema is managed exclusively
      through Flask-Migrate (flask db migrate / flask db upgrade).
"""

import os

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

db = SQLAlchemy()


def _resolve_db_url() -> str:
    """Return the database URL to use, with scheme normalisation."""
    raw = (
        os.environ.get("DATABASE_URL_POOLED", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
        or "sqlite:///local.db"
    )
    # SQLAlchemy ≥ 1.4 dropped the legacy "postgres://" scheme.
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    # SQLAlchemy 2.x defaults to the psycopg (v3) driver; force psycopg2 since
    # only psycopg2-binary is installed.
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        raw = "postgresql+psycopg2://" + raw[len("postgresql://"):]
    return raw


def configure_db(app) -> None:
    """
    Attach SQLAlchemy to *app* using the resolved DATABASE_URL.
    Call this before creating the Migrate instance.
    """
    url = _resolve_db_url()
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    db.init_app(app)
