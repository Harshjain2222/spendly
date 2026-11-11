"""
scripts/migrate_sqlite_to_postgres.py
--------------------------------------
Copies data from an existing Spendly SQLite database to the Postgres (Neon)
database configured via DATABASE_URL in .env.

Usage:
    python scripts/migrate_sqlite_to_postgres.py path/to/spendly.db

Requirements:
    - Run AFTER `flask db upgrade` so the Postgres schema already exists.
    - Idempotent: safe to re-run; existing rows (matched by id) are skipped.
    - Never modifies the SQLite source file (read-only connection).
    - Resets Postgres sequences for users and expenses after copying so that
      subsequent INSERTs get correct auto-increment values.
    - Prints source vs destination row counts at the end.

Notes on data conversion:
    - amount: stored as REAL in SQLite → Decimal rounded to 2 places
    - date: stored as 'YYYY-MM-DD' TEXT in SQLite → Python date object
    - created_at: stored as 'YYYY-MM-DD HH:MM:SS' TEXT → Python datetime
    - password_hash: copied verbatim (no rehashing)
    - ids: preserved exactly (INSERT with explicit id column)
"""

import sys
import os
import sqlite3
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# Bootstrap: make the project root importable so we can load .env / db config
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_postgres_url() -> str:
    """Return the direct (non-pooled) Postgres URL for migrations."""
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is not set in .env — cannot connect to Postgres."
        )
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    # SQLAlchemy 2.x defaults to the psycopg (v3) driver; force psycopg2 since
    # only psycopg2-binary is installed.
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        raw = "postgresql+psycopg2://" + raw[len("postgresql://"):]
    return raw


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        # Try with time component (some SQLite rows may include time)
        return datetime.strptime(value.strip().split(" ")[0], "%Y-%m-%d").date()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    # Strip microseconds
    value = value.split(".")[0]
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None


def _to_decimal(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Main migration logic
# ---------------------------------------------------------------------------

def migrate(sqlite_path: str) -> None:
    if not os.path.isfile(sqlite_path):
        print(f"ERROR: SQLite file not found: {sqlite_path}")
        sys.exit(1)

    # Open SQLite in read-only mode (URI syntax)
    sqlite_uri = f"file:{sqlite_path}?mode=ro"
    sqlite_conn = sqlite3.connect(sqlite_uri, uri=True)
    sqlite_conn.row_factory = sqlite3.Row

    pg_url = _get_postgres_url()
    pg_engine = sa.create_engine(pg_url, pool_pre_ping=True)

    try:
        # ----------------------------------------------------------------
        # Read all rows from SQLite
        # ----------------------------------------------------------------
        src_users = sqlite_conn.execute(
            "SELECT id, name, email, password_hash, created_at FROM users"
        ).fetchall()
        src_expenses = sqlite_conn.execute(
            "SELECT id, user_id, amount, category, date, description, created_at FROM expenses"
        ).fetchall()

        print(f"\nSource (SQLite): {len(src_users)} user(s), {len(src_expenses)} expense(s)")

        with pg_engine.begin() as pg_conn:
            # ----------------------------------------------------------------
            # Migrate users
            # ----------------------------------------------------------------
            users_inserted = 0
            users_skipped = 0
            for row in src_users:
                existing = pg_conn.execute(
                    sa.text("SELECT id FROM users WHERE id = :id"),
                    {"id": row["id"]},
                ).fetchone()
                if existing:
                    users_skipped += 1
                    continue

                created_at = _parse_datetime(row["created_at"]) or datetime.utcnow()
                pg_conn.execute(
                    sa.text(
                        """
                        INSERT INTO users (id, name, email, password_hash, created_at)
                        VALUES (:id, :name, :email, :password_hash, :created_at)
                        """
                    ),
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "email": row["email"],
                        "password_hash": row["password_hash"],
                        "created_at": created_at,
                    },
                )
                users_inserted += 1

            # ----------------------------------------------------------------
            # Migrate expenses
            # ----------------------------------------------------------------
            expenses_inserted = 0
            expenses_skipped = 0
            for row in src_expenses:
                existing = pg_conn.execute(
                    sa.text("SELECT id FROM expenses WHERE id = :id"),
                    {"id": row["id"]},
                ).fetchone()
                if existing:
                    expenses_skipped += 1
                    continue

                expense_date = _parse_date(row["date"])
                created_at = _parse_datetime(row["created_at"]) or datetime.utcnow()
                amount = _to_decimal(row["amount"])

                pg_conn.execute(
                    sa.text(
                        """
                        INSERT INTO expenses
                            (id, user_id, amount, category, date, description, created_at)
                        VALUES
                            (:id, :user_id, :amount, :category, :date, :description, :created_at)
                        """
                    ),
                    {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "amount": amount,
                        "category": row["category"],
                        "date": expense_date,
                        "description": row["description"],
                        "created_at": created_at,
                    },
                )
                expenses_inserted += 1

            # ----------------------------------------------------------------
            # Reset Postgres sequences so future auto-increment is correct
            # ----------------------------------------------------------------
            pg_conn.execute(sa.text(
                "SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 0) + 1, false)"
            ))
            pg_conn.execute(sa.text(
                "SELECT setval('expenses_id_seq', COALESCE((SELECT MAX(id) FROM expenses), 0) + 1, false)"
            ))

        # ----------------------------------------------------------------
        # Verify: destination counts
        # ----------------------------------------------------------------
        with pg_engine.connect() as pg_conn:
            dst_users = pg_conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()
            dst_expenses = pg_conn.execute(sa.text("SELECT COUNT(*) FROM expenses")).scalar()

        print(f"\nMigration complete:")
        print(f"  Users    — source: {len(src_users):>6}  |  destination: {dst_users:>6}  "
              f"| inserted: {users_inserted:>6}  | skipped (already existed): {users_skipped:>6}")
        print(f"  Expenses — source: {len(src_expenses):>6}  |  destination: {dst_expenses:>6}  "
              f"| inserted: {expenses_inserted:>6}  | skipped (already existed): {expenses_skipped:>6}")
        print()

    finally:
        sqlite_conn.close()
        pg_engine.dispose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/migrate_sqlite_to_postgres.py <path-to-sqlite.db>")
        sys.exit(1)

    migrate(sys.argv[1])
