"""
database/queries.py
-------------------
Pure query helpers for the Spendly profile page.
Rewritten to use SQLAlchemy ORM instead of raw sqlite3.
No Flask route logic here — each function uses the db session via SQLAlchemy.
"""

from datetime import datetime, date as date_type
from decimal import Decimal

from sqlalchemy import func, case

from database.db import db
from database.models import User, Expense


# ------------------------------------------------------------------ #
# User                                                                #
# ------------------------------------------------------------------ #

def get_user_by_id(user_id):
    """
    Return a dict with 'name', 'email', 'initials', and 'member_since'
    for the given user_id, or None if not found.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return None

    # Build initials from first two words of name
    parts = user.name.strip().split()
    initials = "".join(p[0].upper() for p in parts[:2]) if parts else "U"

    # Format created_at as "Month YYYY"
    try:
        member_since = user.created_at.strftime("%B %Y")
    except Exception:
        member_since = str(user.created_at)[:7] if user.created_at else "N/A"

    return {
        "name": user.name,
        "email": user.email,
        "initials": initials,
        "member_since": member_since,
    }


# ------------------------------------------------------------------ #
# Summary stats                                                        #
# ------------------------------------------------------------------ #

def get_summary_stats(user_id, date_from=None, date_to=None):
    """
    Return a dict with 'total_spent' (Decimal), 'transaction_count' (int),
    and 'top_category' (str) for the given user_id, optionally filtered by date.
    Returns zero values rather than raising when the user has no expenses.
    """
    q = db.session.query(Expense).filter(Expense.user_id == user_id)

    if date_from and date_to:
        # date_from / date_to arrive as "YYYY-MM-DD" strings from the route
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        q = q.filter(Expense.date.between(d_from, d_to))

    agg = db.session.query(
        func.count(Expense.id).label("total_count"),
        func.coalesce(func.sum(Expense.amount), 0).label("total_spent"),
    ).filter(Expense.user_id == user_id)

    top_q = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label("cat_total"),
    ).filter(Expense.user_id == user_id)

    if date_from and date_to:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        agg = agg.filter(Expense.date.between(d_from, d_to))
        top_q = top_q.filter(Expense.date.between(d_from, d_to))

    agg_row = agg.one()
    top_row = top_q.group_by(Expense.category).order_by(
        func.sum(Expense.amount).desc()
    ).first()

    return {
        "total_spent": float(agg_row.total_spent) if agg_row.total_spent else 0,
        "transaction_count": agg_row.total_count or 0,
        "top_category": top_row.category if top_row else "—",
    }


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
    q = db.session.query(Expense).filter(Expense.user_id == user_id)

    if date_from and date_to:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        q = q.filter(Expense.date.between(d_from, d_to))

    rows = q.order_by(Expense.date.desc(), Expense.id.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "date": r.date.strftime("%Y-%m-%d") if hasattr(r.date, "strftime") else str(r.date),
            "description": r.description,
            "category": r.category,
            "amount": float(r.amount),
        }
        for r in rows
    ]


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
    q = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label("cat_total"),
    ).filter(Expense.user_id == user_id)

    if date_from and date_to:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
        q = q.filter(Expense.date.between(d_from, d_to))

    rows = q.group_by(Expense.category).order_by(
        func.sum(Expense.amount).desc()
    ).all()

    if not rows:
        return []

    total = sum(float(r.cat_total) for r in rows)
    if total == 0:
        return []

    # Largest-remainder method for integer percentages that sum to 100
    raw_pcts = [(float(r.cat_total) / total * 100) for r in rows]
    floor_pcts = [int(p) for p in raw_pcts]
    remainders = [(raw_pcts[i] - floor_pcts[i], i) for i in range(len(rows))]
    deficit = 100 - sum(floor_pcts)

    for _, idx in sorted(remainders, reverse=True)[:deficit]:
        floor_pcts[idx] += 1

    return [
        {
            "category": rows[i].category,
            "amount": float(rows[i].cat_total),
            "percentage": floor_pcts[i],
            "css_class": _bar_class(floor_pcts[i]),
        }
        for i in range(len(rows))
    ]


# ------------------------------------------------------------------ #
# Insert expense                                                      #
# ------------------------------------------------------------------ #

def insert_expense(user_id, amount, category, date, description=None):
    """
    Insert a new expense record for the given user_id.
    Stores None as NULL for empty descriptions.
    Returns the new row ID.
    """
    expense = Expense(
        user_id=user_id,
        amount=amount,
        category=category,
        date=_parse_date(date) if isinstance(date, str) else date,
        description=description,
    )
    db.session.add(expense)
    db.session.commit()
    return expense.id


# ------------------------------------------------------------------ #
# Get / Update / Delete expense (for edit and delete flows)           #
# ------------------------------------------------------------------ #

def get_expense_by_id(expense_id, user_id):
    """
    Return a dict for the expense if it exists AND belongs to the given user_id.
    Returns None otherwise (not found or wrong owner).
    Ownership is enforced at the query level: filter by id AND user_id.
    """
    expense = (
        db.session.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == user_id)
        .first()
    )
    if expense is None:
        return None

    return {
        "id": expense.id,
        "user_id": expense.user_id,
        "amount": float(expense.amount),
        "category": expense.category,
        "date": expense.date.strftime("%Y-%m-%d") if hasattr(expense.date, "strftime") else str(expense.date),
        "description": expense.description,
    }


def update_expense(expense_id, user_id, amount, category, date, description):
    """
    UPDATE the expense row matching both id AND user_id.
    If the expense doesn't exist or belongs to another user, 0 rows are
    affected and no error is raised — a silent no-op that is safe by design.
    """
    expense = (
        db.session.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == user_id)
        .first()
    )
    if expense is None:
        return
    expense.amount = amount
    expense.category = category
    expense.date = _parse_date(date) if isinstance(date, str) else date
    expense.description = description
    db.session.commit()


def delete_expense(expense_id, user_id):
    """
    DELETE the expense row matching both id AND user_id.
    If the expense doesn't exist or belongs to another user, 0 rows are
    affected and no error is raised — a silent no-op that is safe by design.
    """
    expense = (
        db.session.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == user_id)
        .first()
    )
    if expense is None:
        return
    db.session.delete(expense)
    db.session.commit()


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _parse_date(value):
    """Parse a 'YYYY-MM-DD' string to a Python date object."""
    if isinstance(value, (date_type,)):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()
