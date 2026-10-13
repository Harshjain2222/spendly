from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import re
import os
from datetime import datetime
from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "spendly-dev-secret-key-change-in-production")

# ------------------------------------------------------------------ #
# Database bootstrap                                                  #
# ------------------------------------------------------------------ #
with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET" and session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return render_template("register.html", error="All fields are required.", name=name, email=email)

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return render_template("register.html", error="Please enter a valid email address.", name=name, email=email)

        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters long.", name=name, email=email)

        db = get_db()
        try:
            existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                return render_template("register.html", error="Email is already registered.", name=name, email=email)

            password_hash = generate_password_hash(password)
            db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Email is already registered.", name=name, email=email)
        finally:
            db.close()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template("login.html", error="All fields are required.", email=email)

        db = get_db()
        user = db.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.", email=email)

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    db = get_db()
    try:
        # Fetch real user record
        row = db.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if not row:
            session.clear()
            return redirect(url_for("login"))

        # Compute initials and member-since date
        names = row["name"].strip().split()
        initials = "".join([n[0].upper() for n in names[:2]]) if names else "U"
        try:
            raw = row["created_at"].split(".")[0]
            member_since = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").strftime("%B %Y")
        except Exception:
            member_since = row["created_at"][:7] if row["created_at"] else "N/A"

        user = {
            "name": row["name"],
            "email": row["email"],
            "member_since": member_since,
            "initials": initials,
        }

        # Aggregate expense stats for this user
        stats_row = db.execute(
            """SELECT COUNT(*) AS total_count,
                      COALESCE(SUM(amount), 0) AS total_spent
               FROM expenses WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        total_count = stats_row["total_count"]
        total_spent = stats_row["total_spent"]

        # Top category by total spending
        top_cat_row = db.execute(
            """SELECT category, SUM(amount) AS cat_total
               FROM expenses WHERE user_id = ?
               GROUP BY category ORDER BY cat_total DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        top_category = top_cat_row["category"] if top_cat_row else "—"

        stats = {
            "total_spent": total_spent,
            "transaction_count": total_count,
            "top_category": top_category,
        }

        # 5 most recent transactions
        tx_rows = db.execute(
            """SELECT date, description, category, amount
               FROM expenses WHERE user_id = ?
               ORDER BY date DESC, id DESC LIMIT 5""",
            (user_id,),
        ).fetchall()
        recent_transactions = [
            {"date": r["date"], "description": r["description"],
             "category": r["category"], "amount": r["amount"]}
            for r in tx_rows
        ]

        # Category breakdown with percentages
        cat_rows = db.execute(
            """SELECT category, SUM(amount) AS cat_total
               FROM expenses WHERE user_id = ?
               GROUP BY category ORDER BY cat_total DESC""",
            (user_id,),
        ).fetchall()

        # Map percentages to nearest pre-defined CSS width class
        def _bar_class(pct):
            thresholds = [7, 13, 15, 26, 34, 50, 65, 80, 100]
            labels     = [7, 13, 15, 26, 34, 50, 65, 80, 100]
            for t in thresholds:
                if pct <= t:
                    return f"bar-w-{t}"
            return "bar-w-100"

        category_breakdown = []
        for r in cat_rows:
            pct = round((r["cat_total"] / total_spent * 100)) if total_spent else 0
            category_breakdown.append({
                "category": r["category"],
                "amount": r["cat_total"],
                "percentage": pct,
                "css_class": _bar_class(pct),
            })
    finally:
        db.close()

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=recent_transactions,
        categories=category_breakdown,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
