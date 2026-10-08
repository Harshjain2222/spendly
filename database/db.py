import sqlite3
import os
from werkzeug.security import generate_password_hash

# Resolve DB path relative to this file so it always lands in the project root
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "spendly.db")


def get_db():
    """Open and return a SQLite connection with row_factory and FK enforcement."""
    conn = sqlite3.connect(os.path.abspath(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call multiple times."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def seed_db():
    """Insert demo user + 8 sample expenses. Skips if data already exists."""
    conn = get_db()

    # Guard: skip if any users already exist
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    # Insert demo user
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (
            "Demo User",
            "demo@spendly.com",
            generate_password_hash("demo123"),
        ),
    )
    conn.commit()

    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()["id"]

    # 8 sample expenses across all 7 categories, dates in October 2026
    sample_expenses = [
        (user_id, 12.50,  "Food",          "2026-10-01", "Lunch at café"),
        (user_id, 45.00,  "Transport",     "2026-10-03", "Monthly bus pass top-up"),
        (user_id, 120.00, "Bills",         "2026-10-05", "Electricity bill"),
        (user_id, 30.00,  "Health",        "2026-10-07", "Pharmacy — vitamins"),
        (user_id, 25.00,  "Entertainment", "2026-10-08", "Cinema tickets"),
        (user_id, 89.99,  "Shopping",      "2026-10-10", "New headphones"),
        (user_id, 15.75,  "Food",          "2026-10-12", "Grocery run"),
        (user_id, 9.99,   "Other",         "2026-10-15", "Subscription renewal"),
    ]

    conn.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        sample_expenses,
    )
    conn.commit()
    conn.close()
