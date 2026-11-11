from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import IntegrityError
import re
import os
from datetime import datetime, timedelta
import calendar

from dotenv import load_dotenv
load_dotenv()

from chat_client import chat_reply, SessionExpired

from database.db import db, configure_db
from database.models import User, Expense
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    insert_expense,
    get_expense_by_id,
    update_expense,
    delete_expense as delete_expense_query,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "spendly-dev-secret-key-change-in-production")

# ------------------------------------------------------------------ #
# Rate limiter (Flask-Limiter)                                        #
# ------------------------------------------------------------------ #

def _rate_limit_key():
    """Key by user_id when logged in, fall back to IP."""
    uid = session.get("user_id")
    if uid:
        return f"user:{uid}"
    return get_remote_address()

limiter = Limiter(
    key_func=_rate_limit_key,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# ------------------------------------------------------------------ #
# Database setup (Flask-SQLAlchemy + Flask-Migrate)                   #
# Schema is managed via `flask db migrate` / `flask db upgrade`.     #
# ------------------------------------------------------------------ #
configure_db(app)
migrate = Migrate(app, db)


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

        try:
            existing = db.session.query(User).filter_by(email=email).first()
            if existing:
                return render_template("register.html", error="Email is already registered.", name=name, email=email)

            password_hash = generate_password_hash(password)
            new_user = User(name=name, email=email, password_hash=password_hash)
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return render_template("register.html", error="Email is already registered.", name=name, email=email)

        session["user_id"] = new_user.id
        session["user_name"] = new_user.name
        return redirect(url_for("profile"))

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

        user = db.session.query(User).filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            return render_template("login.html", error="Invalid email or password.", email=email)

        session["user_id"] = user.id
        session["user_name"] = user.name
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Authenticated routes                                                #
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

    # Fetch user; clear session and redirect if the record has been deleted
    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    raw_from = request.args.get("date_from", "").strip()
    raw_to = request.args.get("date_to", "").strip()

    date_from = None
    date_to = None

    if raw_from and raw_to:
        try:
            d_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
            d_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
            if d_from > d_to:
                flash("Start date must be before end date.", "error")
            else:
                date_from = raw_from
                date_to = raw_to
        except ValueError:
            # Malformed date string silently falls back to unfiltered view
            pass

    today = datetime.now().date()

    # Preset 1: This Month (first day of current calendar month to last day)
    last_day_of_month = calendar.monthrange(today.year, today.month)[1]
    this_month_from = today.replace(day=1).strftime("%Y-%m-%d")
    this_month_to = today.replace(day=last_day_of_month).strftime("%Y-%m-%d")

    # Preset 2: Last 3 Months (3-month window ending today)
    last_3m_from = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    last_3m_to = today.strftime("%Y-%m-%d")

    # Preset 3: Last 6 Months (6-month window ending today)
    last_6m_from = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    last_6m_to = today.strftime("%Y-%m-%d")

    presets = {
        "this_month": {"date_from": this_month_from, "date_to": this_month_to},
        "last_3_months": {"date_from": last_3m_from, "date_to": last_3m_to},
        "last_6_months": {"date_from": last_6m_from, "date_to": last_6m_to},
    }

    # Determine active preset
    if not date_from and not date_to:
        active_preset = "all_time"
    elif date_from == this_month_from and (date_to == this_month_to or date_to == today.strftime("%Y-%m-%d")):
        active_preset = "this_month"
    elif date_from == last_3m_from and date_to == last_3m_to:
        active_preset = "last_3_months"
    elif date_from == last_6m_from and date_to == last_6m_to:
        active_preset = "last_6_months"
    else:
        active_preset = "custom"

    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    recent_transactions = get_recent_transactions(user_id, limit=10, date_from=date_from, date_to=date_to)
    category_breakdown = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=recent_transactions,
        categories=category_breakdown,
        date_from=date_from,
        date_to=date_to,
        active_preset=active_preset,
        presets=presets,
    )


CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Education",
    "Investments",
    "Other",
]


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        date_raw = request.form.get("date", "").strip()
        description_raw = request.form.get("description", "").strip()
        description = description_raw if description_raw else None

        error = None
        amount = None

        if not amount_raw:
            error = "Amount is required."
        else:
            try:
                amount = float(amount_raw)
                if amount <= 0:
                    error = "Amount must be a positive number greater than 0."
            except ValueError:
                error = "Please enter a valid numeric amount."

        if not error and (not category or category not in CATEGORIES):
            error = "Please select a valid category."

        if not error:
            if not date_raw:
                error = "Date is required."
            else:
                try:
                    datetime.strptime(date_raw, "%Y-%m-%d")
                except ValueError:
                    error = "Please enter a valid date in YYYY-MM-DD format."

        if not error:
            if description and len(description) > 200:
                description = description[:200]

            insert_expense(
                user_id=user_id,
                amount=amount,
                category=category,
                date=date_raw,
                description=description,
            )
            return redirect(url_for("profile"))

        return render_template(
            "add_expense.html",
            error=error,
            categories=CATEGORIES,
            amount=amount_raw,
            category=category,
            date=date_raw,
            description=description_raw,
        )

    today = datetime.now().strftime("%Y-%m-%d")
    return render_template(
        "add_expense.html",
        categories=CATEGORIES,
        date=today,
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        date_raw = request.form.get("date", "").strip()
        description_raw = request.form.get("description", "").strip()
        description = description_raw if description_raw else None

        error = None
        amount = None

        if not amount_raw:
            error = "Amount is required."
        else:
            try:
                amount = float(amount_raw)
                if amount <= 0:
                    error = "Amount must be a positive number greater than 0."
            except ValueError:
                error = "Please enter a valid numeric amount."

        if not error and (not category or category not in CATEGORIES):
            error = "Please select a valid category."

        if not error:
            if not date_raw:
                error = "Date is required."
            else:
                try:
                    datetime.strptime(date_raw, "%Y-%m-%d")
                except ValueError:
                    error = "Please enter a valid date in YYYY-MM-DD format."

        if not error:
            if description and len(description) > 200:
                description = description[:200]

            update_expense(
                expense_id=id,
                user_id=user_id,
                amount=amount,
                category=category,
                date=date_raw,
                description=description,
            )
            return redirect(url_for("profile"))

        # Re-render with submitted (not original) values + error message
        return render_template(
            "edit_expense.html",
            error=error,
            categories=CATEGORIES,
            expense={
                "id": id,
                "amount": amount_raw,
                "category": category,
                "date": date_raw,
                "description": description_raw,
            },
        )

    # GET — render form pre-filled with the current DB values
    return render_template(
        "edit_expense.html",
        categories=CATEGORIES,
        expense=expense,
    )


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    delete_expense_query(id, user_id)
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# AI Chat routes                                                      #
# ------------------------------------------------------------------ #

@app.route("/chat")
def chat():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))
    return render_template("chat.html")


@app.route("/chat/message", methods=["POST"])
@limiter.limit("20 per minute; 100 per day")
def chat_message():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Authentication required."}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    # Validate message
    message = data.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message must be a non-empty string."}), 400
    if len(message) > 1000:
        return jsonify({"error": "message must be 1000 characters or fewer."}), 400

    # Validate history
    history = data.get("history", [])
    if not isinstance(history, list):
        return jsonify({"error": "history must be a list."}), 400
    if len(history) > 10:
        return jsonify({"error": "history may contain at most 10 items."}), 400
    for item in history:
        if not isinstance(item, dict):
            return jsonify({"error": "Each history item must be an object."}), 400
        if item.get("role") not in ("user", "assistant"):
            return jsonify({"error": "Each history item role must be 'user' or 'assistant'."}), 400
        if not isinstance(item.get("content", ""), str):
            return jsonify({"error": "Each history item content must be a string."}), 400

    try:
        try:
            from langchain_openai.chat_models._client_utils import _cached_async_httpx_client
            _cached_async_httpx_client.cache_clear()
        except Exception:
            pass
        reply = chat_reply(user_id, history, message.strip())
        return jsonify({"reply": reply})
    except SessionExpired:
        return jsonify({"error": "Session expired, please log in again."}), 401
    except Exception:
        app.logger.exception("chat_message error for user_id=%s", user_id)
        return jsonify({"error": "Something went wrong, try again."}), 500
    finally:
        try:
            from langchain_openai.chat_models._client_utils import _cached_async_httpx_client
            _cached_async_httpx_client.cache_clear()
        except Exception:
            pass


if __name__ == "__main__":
    app.run(debug=True, port=5001)
