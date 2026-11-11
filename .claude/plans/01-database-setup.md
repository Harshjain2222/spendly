# Implementation Plan: Database Setup (Step 1)

## Goal Description

Replace the stub in `database/db.py` with a working SQLite implementation and wire it into `app.py` so the Spendly app has a functioning data layer on startup.

This is the **foundation step** — all future features (auth, profile, expense tracking) build on this. The database will be created at the project root as `spendly.db`.

No new routes are added. No new pip packages are required.

---

## User Review Required

> [!IMPORTANT]
> The spec allows either `spendly.db` or `expense_tracker.db` as the database filename. This plan uses **`spendly.db`** to match the app name. Change if preferred.

> [!NOTE]
> The 8 seed expenses use **October 2026** (current month) for dates, spread across the month for realism.

---

## Open Questions

> [!IMPORTANT]
> **DB file location:** The spec says "project root". This plan computes the DB path relative to `db.py`'s own location (`../spendly.db`) so it is immune to whatever CWD `flask run` is started from.

---

## Proposed Changes

### Component 1 — Data Layer

#### [MODIFY] `database/db.py`

Full replacement of the stub with three functions:

```python
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
```

**Key design decisions:**
- `_DB_PATH` uses `os.path` relative to `db.py` (`../spendly.db`) so the DB lands in the project root regardless of CWD.
- `executescript()` is used for DDL (it auto-commits); individual DML statements use explicit `commit()`.
- `seed_db()` checks row count before any insert — idempotent across restarts.
- All DML uses `?` parameterized placeholders — no string formatting.

---

### Component 2 — Application Bootstrap

#### [MODIFY] `app.py`

**Diff** (changes only):

```diff
-from flask import Flask, render_template
+from flask import Flask, render_template
+from database.db import get_db, init_db, seed_db

 app = Flask(__name__)

+# ------------------------------------------------------------------ #
+# Database bootstrap                                                  #
+# ------------------------------------------------------------------ #
+with app.app_context():
+    init_db()
+    seed_db()
+

 # ------------------------------------------------------------------ #
 # Routes                                                              #
 # ------------------------------------------------------------------ #
```

The `with app.app_context()` pattern is Flask-idiomatic for startup work and is compatible with Flask 2.3+ (where `before_first_request` was deprecated).

---

## Verification Plan

### Automated Tests

```powershell
.\venv\Scripts\Activate.ps1
pytest -v
```

> [!NOTE]
> No test files exist yet — pytest will exit 0 with "no tests collected". Expected at this stage.

### Manual Verification

1. **Start the app:**
   ```powershell
   .\venv\Scripts\Activate.ps1
   flask --app app run --port 5001
   ```

2. **Confirm `spendly.db` was created:**
   ```powershell
   Test-Path spendly.db   # Expected: True
   ```

3. **Inspect seed data:**
   ```powershell
   python -c "
   from database.db import get_db
   db = get_db()
   users = db.execute('SELECT id, name, email FROM users').fetchall()
   expenses = db.execute('SELECT id, category, amount, date FROM expenses').fetchall()
   print('Users:', [dict(u) for u in users])
   print('Expenses count:', len(expenses))
   for e in expenses: print(' -', dict(e))
   db.close()
   "
   ```
   Expected: 1 user, 8 expenses across all 7 categories.

4. **Idempotency check:** Restart app and re-run step 3. Counts must remain 1 and 8.

5. **Foreign key enforcement:**
   ```powershell
   python -c "
   from database.db import get_db; db = get_db()
   try:
       db.execute('INSERT INTO expenses (user_id,amount,category,date) VALUES (?,?,?,?)', (999,1.0,'Food','2026-10-01'))
       db.commit(); print('FAIL: FK not enforced')
   except Exception as e: print('PASS:', e)
   db.close()
   "
   ```

6. **UNIQUE email constraint:**
   ```powershell
   python -c "
   from database.db import get_db; db = get_db()
   try:
       db.execute('INSERT INTO users (name,email,password_hash) VALUES (?,?,?)', ('X','demo@spendly.com','h'))
       db.commit(); print('FAIL: UNIQUE not enforced')
   except Exception as e: print('PASS:', e)
   db.close()
   "
   ```

---

## Definition of Done Checklist

- [ ] `spendly.db` created on app startup
- [ ] `users` and `expenses` tables exist with correct schema and constraints
- [ ] Demo user exists with hashed password
- [ ] 8 sample expenses exist across all 7 categories
- [ ] No duplicate seed data on repeated runs
- [ ] App starts without errors (`flask run`)
- [ ] Foreign key enforcement works
- [ ] All queries use parameterized SQL
