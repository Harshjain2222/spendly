"""
tests/test_edit_expense.py
--------------------------
Unit and route tests for Step 8: Edit Expense.

Run with:
    pytest tests/test_edit_expense.py -v
"""

import pytest
import sqlite3
from werkzeug.security import generate_password_hash

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.queries import get_expense_by_id, update_expense, insert_expense
import database.db as db_module


# ──────────────────────────────────────────────────────────────
# Helpers
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


def make_in_memory_db():
    """Create a fresh in-memory SQLite DB with schema + one user + one expense."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", generate_password_hash("password123")),
    )
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("test@example.com",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, 50.0, "Food", "2026-10-01", "Lunch"),
    )
    conn.commit()
    return conn, user_id


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

class _NoCloseProxy:
    """
    Thin wrapper that forwards every attribute access to the underlying
    sqlite3.Connection but turns close() into a no-op.  This lets query
    helpers call conn.close() freely without destroying the shared
    in-memory database between calls.
    """
    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)

    def close(self):
        pass  # intentional no-op

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_conn"), name, value)


@pytest.fixture
def mem_db(tmp_path, monkeypatch):
    """
    Unit-test fixture: a fresh SQLite file DB with schema + one user + one expense.
    _DB_PATH is patched so get_db() opens this isolated temp file.
    Yields (connection, user_id) for test assertions.
    """
    db_file = str(tmp_path / "unit_test.db")
    monkeypatch.setattr(db_module, "_DB_PATH", db_file)

    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(db_file)
    conn.row_factory = _sqlite3.Row
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
        (user_id, 50.0, "Food", "2026-10-01", "Lunch"),
    )
    conn.commit()

    yield conn, user_id

    conn.close()


@pytest.fixture
def flask_client(tmp_path, monkeypatch):
    """Flask test client using a temp SQLite file (never touches spendly.db)."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_DB_PATH", db_file)

    # Re-import app *after* patching so init_db() uses the temp file
    import importlib
    import app as app_module
    importlib.reload(app_module)

    app_module.app.config["TESTING"] = True
    app_module.app.config["SECRET_KEY"] = "test-secret"

    with app_module.app.test_client() as client:
        yield client


@pytest.fixture
def auth_client(flask_client):
    """Flask test client with one registered+logged-in user and one expense."""
    flask_client.post("/register", data={
        "name": "Alice",
        "email": "alice@example.com",
        "password": "password123",
    })
    flask_client.post("/login", data={
        "email": "alice@example.com",
        "password": "password123",
    })

    # Insert expense for Alice directly via the DB
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
# Unit tests — get_expense_by_id
# ──────────────────────────────────────────────────────────────

class TestGetExpenseById:
    def test_correct_owner_returns_row(self, mem_db):
        conn, user_id = mem_db
        expense_id = conn.execute(
            "SELECT id FROM expenses WHERE amount = 50.0"
        ).fetchone()["id"]
        row = get_expense_by_id(expense_id, user_id)
        assert row is not None
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-10-01"
        assert row["description"] == "Lunch"

    def test_wrong_owner_returns_none(self, mem_db):
        conn, _ = mem_db
        expense_id = conn.execute(
            "SELECT id FROM expenses WHERE amount = 50.0"
        ).fetchone()["id"]
        row = get_expense_by_id(expense_id, user_id=9999)
        assert row is None

    def test_nonexistent_id_returns_none(self, mem_db):
        _, user_id = mem_db
        row = get_expense_by_id(expense_id=9999, user_id=user_id)
        assert row is None


# ──────────────────────────────────────────────────────────────
# Unit tests — update_expense
# ──────────────────────────────────────────────────────────────

class TestUpdateExpense:
    def test_correct_owner_updates_row(self, mem_db):
        conn, user_id = mem_db
        expense_id = conn.execute(
            "SELECT id FROM expenses WHERE amount = 50.0"
        ).fetchone()["id"]
        update_expense(expense_id, user_id, amount=99.0, category="Health",
                       date="2026-11-01", description="Updated")
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        assert row["amount"] == 99.0
        assert row["category"] == "Health"
        assert row["date"] == "2026-11-01"
        assert row["description"] == "Updated"

    def test_wrong_owner_is_noop(self, mem_db):
        conn, _ = mem_db
        expense_id = conn.execute(
            "SELECT id FROM expenses WHERE amount = 50.0"
        ).fetchone()["id"]
        update_expense(expense_id, user_id=9999, amount=999.0, category="Bills",
                       date="2026-12-01", description="Hacked")
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        # Original values must be untouched
        assert row["amount"] == 50.0
        assert row["category"] == "Food"


# ──────────────────────────────────────────────────────────────
# Route tests — GET /expenses/<id>/edit
# ──────────────────────────────────────────────────────────────

class TestGetEditRoute:
    def test_unauthenticated_redirects_to_login(self, flask_client):
        resp = flask_client.get("/expenses/1/edit")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_own_expense_returns_200_with_prefilled_values(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "75" in body           # amount
        assert "Transport" in body    # category selected
        assert "Bus pass" in body     # description
        assert "2026-10-10" in body   # date

    def test_other_users_expense_returns_404(self, auth_client, flask_client):
        _, _, expense_id = auth_client
        # Log in as Bob (different user)
        flask_client.post("/register", data={"name": "Bob", "email": "bob@example.com", "password": "password123"})
        flask_client.post("/login", data={"email": "bob@example.com", "password": "password123"})
        resp = flask_client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 404

    def test_nonexistent_expense_returns_404(self, auth_client):
        client, _, _ = auth_client
        resp = client.get("/expenses/9999/edit")
        assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# Route tests — POST /expenses/<id>/edit
# ──────────────────────────────────────────────────────────────

class TestPostEditRoute:
    def test_unauthenticated_redirects_to_login(self, flask_client):
        resp = flask_client.post("/expenses/1/edit", data={
            "amount": "100", "category": "Food", "date": "2026-10-01"
        })
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_valid_data_redirects_to_profile(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "120.50",
            "category": "Bills",
            "date": "2026-10-15",
            "description": "Updated bill",
        })
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

    def test_valid_data_persists_to_db(self, auth_client):
        client, _, expense_id = auth_client
        client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "200.0",
            "category": "Shopping",
            "date": "2026-10-20",
            "description": "New shoes",
        })
        db = db_module.get_db()
        row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        db.close()
        assert row["amount"] == 200.0
        assert row["category"] == "Shopping"
        assert row["date"] == "2026-10-20"
        assert row["description"] == "New shoes"

    def test_other_users_expense_returns_404(self, auth_client, flask_client):
        _, _, expense_id = auth_client
        flask_client.post("/register", data={"name": "Bob", "email": "bob@example.com", "password": "password123"})
        flask_client.post("/login", data={"email": "bob@example.com", "password": "password123"})
        resp = flask_client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "1.0", "category": "Food", "date": "2026-01-01"
        })
        assert resp.status_code == 404

    def test_missing_amount_rerenders_with_error(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "", "category": "Food", "date": "2026-10-01"
        })
        assert resp.status_code == 200
        body = resp.data.decode().lower()
        assert "required" in body or "amount" in body

    def test_zero_amount_rerenders_with_error(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "0", "category": "Food", "date": "2026-10-01"
        })
        assert resp.status_code == 200
        body = resp.data.decode().lower()
        assert "positive" in body or "greater" in body

    def test_nonnumeric_amount_rerenders_with_error(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "abc", "category": "Food", "date": "2026-10-01"
        })
        assert resp.status_code == 200
        assert "valid" in resp.data.decode().lower()

    def test_invalid_category_rerenders_with_error(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50", "category": "NotARealCategory", "date": "2026-10-01"
        })
        assert resp.status_code == 200
        assert "category" in resp.data.decode().lower()

    def test_invalid_date_rerenders_with_error(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50", "category": "Food", "date": "not-a-date"
        })
        assert resp.status_code == 200
        assert "date" in resp.data.decode().lower()

    def test_no_description_stores_null_and_redirects(self, auth_client):
        client, _, expense_id = auth_client
        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50", "category": "Food", "date": "2026-10-01", "description": ""
        })
        assert resp.status_code == 302
        db = db_module.get_db()
        row = db.execute("SELECT description FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        db.close()
        assert row["description"] is None
