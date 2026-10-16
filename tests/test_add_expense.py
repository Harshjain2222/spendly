"""
tests/test_add_expense.py
-------------------------
Unit and route tests for Step 7 — Add Expense.

Tests insert_expense in database/queries.py and route-level handling,
authentication guards, and validation in app.py.
"""

import sqlite3
import pytest
from werkzeug.security import generate_password_hash


DDL = """
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

EXPECTED_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def _make_connection(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _seed(db_path):
    conn = _make_connection(db_path)
    conn.executescript(DDL)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Test Expense User", "expenseuser@spendly.com", generate_password_hash("testpass"), "2026-01-01 00:00:00"),
    )
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("expenseuser@spendly.com",)
    ).fetchone()["id"]
    conn.close()
    return user_id


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_add_expense.db")
    user_id = _seed(db_path)
    yield db_path, user_id


@pytest.fixture()
def patched_db(tmp_db, monkeypatch):
    db_path, user_id = tmp_db

    def fake_get_db():
        return _make_connection(db_path)

    import database.db as db_mod
    import database.queries as q_mod
    monkeypatch.setattr(db_mod, "get_db", fake_get_db)
    monkeypatch.setattr(q_mod, "get_db", fake_get_db)

    yield db_path, user_id


@pytest.fixture()
def flask_client(tmp_db, monkeypatch):
    db_path, user_id = tmp_db

    def fake_get_db():
        return _make_connection(db_path)

    import database.db as db_mod
    import database.queries as q_mod
    monkeypatch.setattr(db_mod, "get_db", fake_get_db)
    monkeypatch.setattr(q_mod, "get_db", fake_get_db)
    monkeypatch.setattr(db_mod, "init_db", lambda: None)
    monkeypatch.setattr(db_mod, "seed_db", lambda: None)

    from app import app as flask_app
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with flask_app.test_client() as c:
        yield c, db_path, user_id


# ---------------------------------------------------------------------------
# Unit tests — insert_expense
# ---------------------------------------------------------------------------

class TestInsertExpense:
    def test_insert_expense_valid(self, patched_db):
        db_path, user_id = patched_db
        from database.queries import insert_expense

        row_id = insert_expense(
            user_id=user_id,
            amount=50.0,
            category="Food",
            date="2026-03-20",
            description="Lunch",
        )
        assert row_id is not None

        conn = _make_connection(db_path)
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (row_id,)).fetchone()
        conn.close()

        assert row is not None
        assert row["user_id"] == user_id
        assert abs(row["amount"] - 50.0) < 0.001
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_insert_expense_null_description(self, patched_db):
        db_path, user_id = patched_db
        from database.queries import insert_expense

        row_id = insert_expense(
            user_id=user_id,
            amount=30.0,
            category="Transport",
            date="2026-03-21",
            description=None,
        )
        assert row_id is not None

        conn = _make_connection(db_path)
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (row_id,)).fetchone()
        conn.close()

        assert row is not None
        assert row["description"] is None


# ---------------------------------------------------------------------------
# Route tests — GET /expenses/add
# ---------------------------------------------------------------------------

class TestGetAddExpenseRoute:
    def test_get_unauthenticated_redirects_to_login(self, flask_client):
        c, _, _ = flask_client
        response = c.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_get_authenticated_renders_form(self, flask_client):
        c, _, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/expenses/add")
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Must contain form with method POST
        assert 'method="POST"' in html or 'method="post"' in html
        # Must contain all 7 categories
        for cat in EXPECTED_CATEGORIES:
            assert cat in html


# ---------------------------------------------------------------------------
# Route tests — POST /expenses/add
# ---------------------------------------------------------------------------

class TestPostAddExpenseRoute:
    def test_post_unauthenticated_redirects_to_login(self, flask_client):
        c, _, _ = flask_client
        response = c.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_authenticated_valid_data(self, flask_client):
        c, db_path, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        conn = _make_connection(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND category = 'Food'",
            (user_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert abs(row["amount"] - 50.0) < 0.001
        assert row["description"] == "Lunch"

    def test_post_authenticated_missing_amount(self, flask_client):
        c, _, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 200
        assert b"Amount is required" in response.data or b"amount" in response.data.lower()

    def test_post_authenticated_zero_amount(self, flask_client):
        c, _, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 200
        assert b"positive number" in response.data or b"greater than 0" in response.data

    def test_post_authenticated_non_numeric_amount(self, flask_client):
        c, _, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 200
        assert b"valid" in response.data.lower()

    def test_post_authenticated_invalid_category(self, flask_client):
        c, _, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "InvalidCategory",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 200
        assert b"category" in response.data.lower()

    def test_post_authenticated_invalid_date(self, flask_client):
        c, _, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "Lunch",
            },
        )
        assert response.status_code == 200
        assert b"date" in response.data.lower()

    def test_post_authenticated_no_description_stores_null(self, flask_client):
        c, db_path, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.post(
            "/expenses/add",
            data={
                "amount": "75.50",
                "category": "Transport",
                "date": "2026-03-20",
                "description": "",
            },
        )
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        conn = _make_connection(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND category = 'Transport'",
            (user_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["description"] is None
