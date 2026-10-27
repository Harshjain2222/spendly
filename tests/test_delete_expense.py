"""
tests/test_delete_expense.py
----------------------------
Unit and route tests for Step 9: Delete Expense.

Run with:
    pytest tests/test_delete_expense.py -v
"""

import pytest
import sqlite3
import sys
import os
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.queries import delete_expense
import database.db as db_module


# ──────────────────────────────────────────────────────────────
# Helpers & Schema
# ──────────────────────────────────────────────────────────────

SCHEMA = """
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
"""


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def unit_db(tmp_path, monkeypatch):
    """
    Unit-test fixture: isolated SQLite database with one user and one expense.
    _DB_PATH is patched so get_db() opens this isolated file.
    Yields (connection, user_id, expense_id).
    """
    db_file = str(tmp_path / "unit_delete_test.db")
    monkeypatch.setattr(db_module, "_DB_PATH", db_file)

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)

    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", generate_password_hash("password123")),
    )
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("test@example.com",)
    ).fetchone()["id"]

    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, 45.0, "Food", "2026-10-01", "Dinner"),
    )
    conn.commit()
    expense_id = conn.execute(
        "SELECT id FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchone()["id"]

    yield conn, user_id, expense_id

    conn.close()


@pytest.fixture
def flask_client(tmp_path, monkeypatch):
    """Flask test client using an isolated temp SQLite file."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_DB_PATH", db_file)

    import importlib
    import app as app_module
    importlib.reload(app_module)

    app_module.app.config["TESTING"] = True
    app_module.app.config["SECRET_KEY"] = "test-secret"

    with app_module.app.test_client() as client:
        yield client


@pytest.fixture
def seeded_client(flask_client):
    """Client with one registered and logged-in user plus one expense created."""
    flask_client.post("/register", data={
        "name": "Alice",
        "email": "alice@example.com",
        "password": "password123",
    })
    flask_client.post("/login", data={
        "email": "alice@example.com",
        "password": "password123",
    })

    db = db_module.get_db()
    user = db.execute(
        "SELECT id FROM users WHERE email = ?", ("alice@example.com",)
    ).fetchone()
    user_id = user["id"]

    cursor = db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, 75.0, "Transport", "2026-10-10", "Bus pass"),
    )
    db.commit()
    expense_id = cursor.lastrowid
    db.close()

    return flask_client, user_id, expense_id


# ──────────────────────────────────────────────────────────────
# Unit tests — delete_expense
# ──────────────────────────────────────────────────────────────

class TestDeleteExpenseUnit:
    def test_valid_expense_correct_owner_removes_row(self, unit_db):
        conn, user_id, expense_id = unit_db
        delete_expense(expense_id, user_id)
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        assert row is None

    def test_valid_expense_wrong_owner_leaves_row_intact(self, unit_db):
        conn, _, expense_id = unit_db
        delete_expense(expense_id, user_id=9999)
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        assert row is not None
        assert row["amount"] == 45.0

    def test_nonexistent_expense_is_noop(self, unit_db):
        conn, user_id, _ = unit_db
        delete_expense(99999, user_id)
        # Should not raise any error and existing row count remains 1
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        assert count == 1


# ──────────────────────────────────────────────────────────────
# Route tests — POST & GET /expenses/<id>/delete
# ──────────────────────────────────────────────────────────────

class TestDeleteExpenseRoute:
    def test_post_delete_unauthenticated_redirects_to_login(self, flask_client):
        resp = flask_client.post("/expenses/1/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_delete_own_expense_redirects_and_deletes_row(self, seeded_client):
        client, _, expense_id = seeded_client
        resp = client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        db = db_module.get_db()
        row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        db.close()
        assert row is None

    def test_post_delete_other_users_expense_returns_404(self, seeded_client, flask_client):
        _, _, expense_id = seeded_client

        # Register and log in as Bob
        flask_client.post("/register", data={
            "name": "Bob",
            "email": "bob@example.com",
            "password": "password123",
        })
        flask_client.post("/login", data={
            "email": "bob@example.com",
            "password": "password123",
        })

        resp = flask_client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 404

        # Expense should still exist
        db = db_module.get_db()
        row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        db.close()
        assert row is not None

    def test_post_delete_nonexistent_expense_returns_404(self, seeded_client):
        client, _, _ = seeded_client
        resp = client.post("/expenses/99999/delete")
        assert resp.status_code == 404

    def test_get_delete_returns_405_method_not_allowed(self, seeded_client):
        client, _, expense_id = seeded_client
        resp = client.get(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 405
