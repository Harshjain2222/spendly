"""
tests/test_06_date_filter_profile.py
------------------------------------
Unit and route tests for Step 6 — Date Filter for Profile Page.

Validates query filters in database/queries.py and route-level parameter
handling, validation, fallbacks, preset highlighting, and error flashing in app.py.
"""

import sqlite3
from datetime import datetime, timedelta
import calendar
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

# Test expenses with dates spanning across October 2026
# and a couple in earlier months for date-filtering tests
SEED_EXPENSES = [
    (100.00, "Bills",         "2026-10-01", "Internet bill"),
    (50.00,  "Food",          "2026-10-05", "Groceries"),
    (30.00,  "Transport",     "2026-10-10", "Fuel"),
    (150.00, "Shopping",      "2026-10-15", "Shoes"),
    (80.00,  "Entertainment", "2026-08-15", "Concert ticket"),
    (40.00,  "Food",          "2026-05-10", "Old restaurant bill"),
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
        ("Test Filter User", "filter@spendly.com", generate_password_hash("pass123"), "2026-01-01 00:00:00"),
    )
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("filter@spendly.com",)
    ).fetchone()["id"]

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(user_id, *row) for row in SEED_EXPENSES],
    )
    conn.commit()
    conn.close()
    return user_id


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_filter.db")
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

    yield user_id


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
        yield c, user_id


# ---------------------------------------------------------------------------
# Unit tests — queries with date filters
# ---------------------------------------------------------------------------

class TestQueriesDateFilter:
    def test_summary_stats_filtered_range(self, patched_db):
        user_id = patched_db
        from database.queries import get_summary_stats

        # Range 2026-10-01 to 2026-10-05 has Bills(100) and Food(50) = 150.00
        stats = get_summary_stats(user_id, date_from="2026-10-01", date_to="2026-10-05")
        assert stats["transaction_count"] == 2
        assert abs(stats["total_spent"] - 150.00) < 0.01
        assert stats["top_category"] == "Bills"

    def test_summary_stats_no_matching_dates(self, patched_db):
        user_id = patched_db
        from database.queries import get_summary_stats

        stats = get_summary_stats(user_id, date_from="2025-01-01", date_to="2025-01-31")
        assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    def test_summary_stats_unfiltered(self, patched_db):
        user_id = patched_db
        from database.queries import get_summary_stats

        stats = get_summary_stats(user_id)
        assert stats["transaction_count"] == 6
        assert abs(stats["total_spent"] - 450.00) < 0.01

    def test_recent_transactions_filtered(self, patched_db):
        user_id = patched_db
        from database.queries import get_recent_transactions

        txns = get_recent_transactions(user_id, limit=10, date_from="2026-10-01", date_to="2026-10-10")
        assert len(txns) == 3
        dates = [t["date"] for t in txns]
        assert dates == ["2026-10-10", "2026-10-05", "2026-10-01"]

    def test_recent_transactions_empty_range(self, patched_db):
        user_id = patched_db
        from database.queries import get_recent_transactions

        txns = get_recent_transactions(user_id, limit=10, date_from="2025-01-01", date_to="2025-01-31")
        assert txns == []

    def test_category_breakdown_filtered(self, patched_db):
        user_id = patched_db
        from database.queries import get_category_breakdown

        # Range 2026-10-01 to 2026-10-05: Bills (100) and Food (50), total 150
        cats = get_category_breakdown(user_id, date_from="2026-10-01", date_to="2026-10-05")
        assert len(cats) == 2
        assert sum(c["percentage"] for c in cats) == 100
        assert cats[0]["category"] == "Bills"
        assert cats[0]["amount"] == 100.00

    def test_category_breakdown_empty_range(self, patched_db):
        user_id = patched_db
        from database.queries import get_category_breakdown

        cats = get_category_breakdown(user_id, date_from="2025-01-01", date_to="2025-01-31")
        assert cats == []


# ---------------------------------------------------------------------------
# Route tests — GET /profile with date filters
# ---------------------------------------------------------------------------

class TestProfileRouteDateFilter:
    def test_unfiltered_profile_renders_all_time_active(self, flask_client):
        c, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/profile")
        assert response.status_code == 200
        # All time button is active
        assert b"btn-preset active" in response.data or b"btn-preset  active" in response.data
        assert b"All Time" in response.data
        assert b"6 entries" in response.data
        assert "₹450.00".encode("utf-8") in response.data

    def test_custom_valid_range_filters_data(self, flask_client):
        c, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/profile?date_from=2026-10-01&date_to=2026-10-05")
        assert response.status_code == 200
        assert b"2 entries" in response.data
        assert "₹150.00".encode("utf-8") in response.data
        assert b"Internet bill" in response.data
        assert b"Groceries" in response.data
        assert b"Shoes" not in response.data

    def test_inverted_range_shows_flash_error_and_falls_back(self, flask_client):
        c, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/profile?date_from=2026-10-15&date_to=2026-10-01")
        assert response.status_code == 200
        # Flash message shown
        assert b"Start date must be before end date." in response.data
        # Falls back to unfiltered (all 6 entries)
        assert b"6 entries" in response.data

    def test_malformed_date_falls_back_silently(self, flask_client):
        c, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/profile?date_from=not-a-date&date_to=2026-10-10")
        assert response.status_code == 200
        assert b"Start date must be before end date." not in response.data
        assert b"6 entries" in response.data

    def test_single_date_param_falls_back_silently(self, flask_client):
        c, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/profile?date_from=2026-10-01")
        assert response.status_code == 200
        assert b"6 entries" in response.data

    def test_range_with_no_expenses_shows_zeroes(self, flask_client):
        c, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/profile?date_from=2025-01-01&date_to=2025-01-31")
        assert response.status_code == 200
        assert "₹0.00".encode("utf-8") in response.data
        assert b"0 entries" in response.data
        assert b"No transactions found for the selected period." in response.data
        assert b"No expense categories found for this period." in response.data

    def test_preset_links_rendered(self, flask_client):
        c, user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id

        response = c.get("/profile")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "This Month" in html
        assert "Last 3 Months" in html
        assert "Last 6 Months" in html
        assert "All Time" in html
        assert 'name="date_from"' in html
        assert 'name="date_to"' in html
