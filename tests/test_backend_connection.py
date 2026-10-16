"""
tests/test_backend_connection.py
---------------------------------
Unit and route tests for Step 5 — Backend Connection.

Each fixture writes to a uniquely named temp file on disk (avoids all
SQLite shared-cache complexity) and patches get_db() in both db and
queries modules so no test ever touches spendly.db.
"""

import os
import sqlite3
import tempfile
import pytest
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

SEED_EXPENSES = [
    (12.50,  "Food",          "2026-10-01", "Lunch at café"),
    (45.00,  "Transport",     "2026-10-03", "Monthly bus pass top-up"),
    (120.00, "Bills",         "2026-10-05", "Electricity bill"),
    (30.00,  "Health",        "2026-10-07", "Pharmacy — vitamins"),
    (25.00,  "Entertainment", "2026-10-08", "Cinema tickets"),
    (89.99,  "Shopping",      "2026-10-10", "New headphones"),
    (15.75,  "Food",          "2026-10-12", "Grocery run"),
    (9.99,   "Other",         "2026-10-15", "Subscription renewal"),
]

# Sum: 12.50 + 45.00 + 120.00 + 30.00 + 25.00 + 89.99 + 15.75 + 9.99 = 348.23
EXPECTED_TOTAL = 348.23


def _make_connection(db_path):
    """Open a sqlite3 connection with row_factory and FK enforcement."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _seed(db_path):
    """Create schema, insert demo user + expenses + empty user. Return (user_id, empty_user_id)."""
    conn = _make_connection(db_path)
    conn.executescript(DDL)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:30:00"),
    )
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()["id"]

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(user_id, *row) for row in SEED_EXPENSES],
    )

    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty User", "empty@spendly.com", generate_password_hash("empty123")),
    )
    conn.commit()
    empty_user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("empty@spendly.com",)
    ).fetchone()["id"]

    conn.close()
    return user_id, empty_user_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Yield path to a seeded temporary SQLite file."""
    db_path = str(tmp_path / "test_spendly.db")
    user_id, empty_user_id = _seed(db_path)
    yield db_path, user_id, empty_user_id


@pytest.fixture()
def patched_db(tmp_db, monkeypatch):
    """
    Patch get_db() in both database.db and database.queries to point at the
    temp DB, then yield (user_id, empty_user_id).
    """
    db_path, user_id, empty_user_id = tmp_db

    def fake_get_db():
        return _make_connection(db_path)

    import database.db as db_mod
    import database.queries as q_mod
    monkeypatch.setattr(db_mod, "get_db", fake_get_db)
    monkeypatch.setattr(q_mod, "get_db", fake_get_db)

    yield user_id, empty_user_id


@pytest.fixture()
def flask_client(tmp_db, monkeypatch):
    """
    Flask test client wired to the temp DB.
    Stubs out init_db / seed_db so app startup doesn't touch disk.
    """
    db_path, user_id, empty_user_id = tmp_db

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
        yield c, user_id, empty_user_id


# ---------------------------------------------------------------------------
# Unit tests — get_user_by_id
# ---------------------------------------------------------------------------

class TestGetUserById:
    def test_valid_user_returns_correct_fields(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_user_by_id
        result = get_user_by_id(user_id)

        assert result is not None
        assert result["name"] == "Demo User"
        assert result["email"] == "demo@spendly.com"
        assert "initials" in result
        assert "member_since" in result

    def test_initials_computed_correctly(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_user_by_id
        result = get_user_by_id(user_id)
        assert result["initials"] == "DU"  # Demo User → D + U

    def test_member_since_formatted_as_month_year(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_user_by_id
        result = get_user_by_id(user_id)
        # created_at is "2026-01-15 10:30:00" → "January 2026"
        assert result["member_since"] == "January 2026"

    def test_nonexistent_user_returns_none(self, patched_db):
        from database.queries import get_user_by_id
        assert get_user_by_id(99999) is None


# ---------------------------------------------------------------------------
# Unit tests — get_summary_stats
# ---------------------------------------------------------------------------

class TestGetSummaryStats:
    def test_user_with_expenses_returns_correct_stats(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_summary_stats
        result = get_summary_stats(user_id)

        assert result["transaction_count"] == 8
        assert abs(result["total_spent"] - EXPECTED_TOTAL) < 0.01
        assert result["top_category"] == "Bills"

    def test_user_with_no_expenses_returns_zeros(self, patched_db):
        _, empty_user_id = patched_db
        from database.queries import get_summary_stats
        result = get_summary_stats(empty_user_id)

        assert result == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


# ---------------------------------------------------------------------------
# Unit tests — get_recent_transactions
# ---------------------------------------------------------------------------

class TestGetRecentTransactions:
    def test_returns_list_ordered_newest_first(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_recent_transactions
        txns = get_recent_transactions(user_id, limit=10)

        assert len(txns) == 8
        dates = [t["date"] for t in txns]
        assert dates == sorted(dates, reverse=True)

    def test_each_item_has_required_keys(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_recent_transactions
        txns = get_recent_transactions(user_id, limit=10)

        for tx in txns:
            assert "date" in tx
            assert "description" in tx
            assert "category" in tx
            assert "amount" in tx

    def test_limit_is_respected(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_recent_transactions
        txns = get_recent_transactions(user_id, limit=3)
        assert len(txns) == 3

    def test_empty_user_returns_empty_list(self, patched_db):
        _, empty_user_id = patched_db
        from database.queries import get_recent_transactions
        assert get_recent_transactions(empty_user_id) == []


# ---------------------------------------------------------------------------
# Unit tests — get_category_breakdown
# ---------------------------------------------------------------------------

class TestGetCategoryBreakdown:
    def test_category_count_is_correct(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_category_breakdown
        cats = get_category_breakdown(user_id)
        # 7 distinct categories: Food(merged), Transport, Bills, Health,
        # Entertainment, Shopping, Other
        assert len(cats) == 7

    def test_percentages_sum_to_100(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_category_breakdown
        cats = get_category_breakdown(user_id)
        assert sum(c["percentage"] for c in cats) == 100

    def test_each_item_has_required_keys(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_category_breakdown
        cats = get_category_breakdown(user_id)
        for cat in cats:
            assert "category" in cat
            assert "amount" in cat
            assert "percentage" in cat
            assert "css_class" in cat

    def test_ordered_by_amount_descending(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_category_breakdown
        cats = get_category_breakdown(user_id)
        amounts = [c["amount"] for c in cats]
        assert amounts == sorted(amounts, reverse=True)

    def test_percentages_are_integers(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_category_breakdown
        cats = get_category_breakdown(user_id)
        for cat in cats:
            assert isinstance(cat["percentage"], int)

    def test_empty_user_returns_empty_list(self, patched_db):
        _, empty_user_id = patched_db
        from database.queries import get_category_breakdown
        assert get_category_breakdown(empty_user_id) == []

    def test_top_category_is_bills(self, patched_db):
        user_id, _ = patched_db
        from database.queries import get_category_breakdown
        cats = get_category_breakdown(user_id)
        # Bills (120.00) should be first
        assert cats[0]["category"] == "Bills"


# ---------------------------------------------------------------------------
# Route tests — GET /profile
# ---------------------------------------------------------------------------

class TestProfileRoute:
    def test_unauthenticated_redirects_to_login(self, flask_client):
        c, _, _ = flask_client
        response = c.get("/profile")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_authenticated_returns_200(self, flask_client):
        c, user_id, _ = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
        response = c.get("/profile")
        assert response.status_code == 200

    def test_response_contains_user_name(self, flask_client):
        c, user_id, _ = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
        response = c.get("/profile")
        assert b"Demo User" in response.data

    def test_response_contains_user_email(self, flask_client):
        c, user_id, _ = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
        response = c.get("/profile")
        assert b"demo@spendly.com" in response.data

    def test_response_contains_rupee_symbol(self, flask_client):
        c, user_id, _ = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
        response = c.get("/profile")
        assert "₹".encode("utf-8") in response.data

    def test_top_category_is_bills(self, flask_client):
        c, user_id, _ = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
        response = c.get("/profile")
        assert b"Bills" in response.data

    def test_transaction_count_shown(self, flask_client):
        c, user_id, _ = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
        response = c.get("/profile")
        # Template renders "{{ transactions|length }} entries"
        assert b"8 entries" in response.data

    def test_empty_user_shows_zero_total(self, flask_client):
        c, _, empty_user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = empty_user_id
        response = c.get("/profile")
        assert response.status_code == 200
        assert "₹0.00".encode("utf-8") in response.data

    def test_empty_user_shows_zero_transactions(self, flask_client):
        c, _, empty_user_id = flask_client
        with c.session_transaction() as sess:
            sess["user_id"] = empty_user_id
        response = c.get("/profile")
        assert b"0 entries" in response.data
