"""
database/queries.py
-------------------
Pure query helpers for the Spendly profile page.
No Flask imports — each function opens and closes its own connection via get_db().
"""

from datetime import datetime
from database.db import get_db


# ------------------------------------------------------------------ #
# User                                                                #
# ------------------------------------------------------------------ #

def get_user_by_id(user_id):
    """
    Return a dict with 'name', 'email', 'initials', and 'member_since'
    for the given user_id, or None if not found.
    """
    db = get_db()
    try:
        row = db.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            return None

        # Build initials from first two words of name
        parts = row["name"].strip().split()
        initials = "".join(p[0].upper() for p in parts[:2]) if parts else "U"

        # Parse created_at and format as "Month YYYY"
        try:
            raw = row["created_at"].split(".")[0]  # strip microseconds
            member_since = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").strftime("%B %Y")
        except Exception:
            member_since = row["created_at"][:7] if row["created_at"] else "N/A"

        return {
            "name": row["name"],
            "email": row["email"],
            "initials": initials,
            "member_since": member_since,
        }
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Summary stats                                                        #
# ------------------------------------------------------------------ #

def get_summary_stats(user_id, date_from=None, date_to=None):
    """
    Return a dict with 'total_spent' (float), 'transaction_count' (int),
    and 'top_category' (str) for the given user_id, optionally filtered by date.
    Returns zero values rather than raising when the user has no expenses.
    """
    db = get_db()
    try:
        if date_from and date_to:
            stats_row = db.execute(
                """SELECT COUNT(*) AS total_count,
                          COALESCE(SUM(amount), 0) AS total_spent
                   FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?""",
                (user_id, date_from, date_to),
            ).fetchone()

            top_row = db.execute(
                """SELECT category, SUM(amount) AS cat_total
                   FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?
                   GROUP BY category ORDER BY cat_total DESC LIMIT 1""",
                (user_id, date_from, date_to),
            ).fetchone()
        else:
            stats_row = db.execute(
                """SELECT COUNT(*) AS total_count,
                          COALESCE(SUM(amount), 0) AS total_spent
                   FROM expenses WHERE user_id = ?""",
                (user_id,),
            ).fetchone()

            top_row = db.execute(
                """SELECT category, SUM(amount) AS cat_total
                   FROM expenses WHERE user_id = ?
                   GROUP BY category ORDER BY cat_total DESC LIMIT 1""",
                (user_id,),
            ).fetchone()

        return {
            "total_spent": stats_row["total_spent"] if stats_row and stats_row["total_spent"] else 0,
            "transaction_count": stats_row["total_count"] if stats_row and stats_row["total_count"] else 0,
            "top_category": top_row["category"] if top_row else "—",
        }
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Recent transactions                                                  #
# ------------------------------------------------------------------ #

def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """
    Return a list of dicts (newest first), each with 'id', 'date',
    'description', 'category', and 'amount', optionally filtered by date.
    The 'id' field is included so templates can build edit/delete links.
    Returns an empty list when there are no expenses.
    """
    db = get_db()
    try:
        if date_from and date_to:
            rows = db.execute(
                """SELECT id, date, description, category, amount
                   FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?
                   ORDER BY date DESC, id DESC LIMIT ?""",
                (user_id, date_from, date_to, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT id, date, description, category, amount
                   FROM expenses WHERE user_id = ?
                   ORDER BY date DESC, id DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()

        return [
            {
                "id": r["id"],
                "date": r["date"],
                "description": r["description"],
                "category": r["category"],
                "amount": r["amount"],
            }
            for r in rows
        ]
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Category breakdown                                                   #
# ------------------------------------------------------------------ #

def _bar_class(pct):
    """Map a percentage to the nearest pre-defined CSS bar-width class."""
    thresholds = [7, 13, 15, 26, 34, 50, 65, 80, 100]
    for t in thresholds:
        if pct <= t:
            return f"bar-w-{t}"
    return "bar-w-100"


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """
    Return a list of dicts ordered by amount descending, each with:
      'category', 'amount', 'percentage' (int), 'css_class', optionally filtered by date.

    Percentages are computed using the largest-remainder method so they
    always sum to exactly 100 (or 0 when the user has no expenses).
    Returns an empty list when there are no expenses.
    """
    db = get_db()
    try:
        if date_from and date_to:
            rows = db.execute(
                """SELECT category, SUM(amount) AS cat_total
                   FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?
                   GROUP BY category ORDER BY cat_total DESC""",
                (user_id, date_from, date_to),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT category, SUM(amount) AS cat_total
                   FROM expenses WHERE user_id = ?
                   GROUP BY category ORDER BY cat_total DESC""",
                (user_id,),
            ).fetchall()

        if not rows:
            return []

        total = sum(r["cat_total"] for r in rows)
        if total == 0:
            return []

        # Compute raw (float) percentages then apply largest-remainder method
        raw_pcts = [(r["cat_total"] / total * 100) for r in rows]
        floor_pcts = [int(p) for p in raw_pcts]
        remainders = [(raw_pcts[i] - floor_pcts[i], i) for i in range(len(rows))]
        deficit = 100 - sum(floor_pcts)

        # Give extra 1 % to the categories with the largest remainders
        for _, idx in sorted(remainders, reverse=True)[:deficit]:
            floor_pcts[idx] += 1

        return [
            {
                "category": rows[i]["category"],
                "amount": rows[i]["cat_total"],
                "percentage": floor_pcts[i],
                "css_class": _bar_class(floor_pcts[i]),
            }
            for i in range(len(rows))
        ]
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Insert expense                                                      #
# ------------------------------------------------------------------ #

def insert_expense(user_id, amount, category, date, description=None):
    """
    Insert a new expense record for the given user_id.
    Stores None as NULL in SQLite for empty descriptions.
    Returns the new row ID.
    """
    db = get_db()
    try:
        cursor = db.execute(
            """INSERT INTO expenses (user_id, amount, category, date, description)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, amount, category, date, description),
        )
        db.commit()
        return cursor.lastrowid
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Get / Update expense (for edit flow)                               #
# ------------------------------------------------------------------ #

def get_expense_by_id(expense_id, user_id):
    """
    Return a single expense row as a sqlite3.Row if it exists AND belongs to
    the given user_id. Returns None otherwise (not found or wrong owner).
    Ownership is enforced at the SQL level: WHERE id = ? AND user_id = ?.
    """
    db = get_db()
    try:
        return db.execute(
            """SELECT id, user_id, amount, category, date, description
               FROM expenses WHERE id = ? AND user_id = ?""",
            (expense_id, user_id),
        ).fetchone()
    finally:
        db.close()


def update_expense(expense_id, user_id, amount, category, date, description):
    """
    UPDATE the expense row matching both id AND user_id.
    If the expense doesn't exist or belongs to another user, 0 rows are
    affected and no error is raised — a silent no-op that is safe by design.
    """
    db = get_db()
    try:
        db.execute(
            """UPDATE expenses
               SET amount = ?, category = ?, date = ?, description = ?
               WHERE id = ? AND user_id = ?""",
            (amount, category, date, description, expense_id, user_id),
        )
        db.commit()
    finally:
        db.close()


def delete_expense(expense_id, user_id):
    """
    DELETE the expense row matching both id AND user_id.
    If the expense doesn't exist or belongs to another user, 0 rows are
    affected and no error is raised — a silent no-op that is safe by design.
    """
    db = get_db()
    try:
        db.execute(
            """DELETE FROM expenses WHERE id = ? AND user_id = ?""",
            (expense_id, user_id),
        )
        db.commit()
    finally:
        db.close()
