import math
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session
from werkzeug.security import check_password_hash
from database.db import (
    get_db, init_db, seed_db,
    create_user, get_user_by_email, get_user_by_id,
    get_expense_summary, update_user, update_password,
    create_expense, get_expense_by_id, get_expenses_for_user, update_expense,
    delete_expense as db_delete_expense,
)

app = Flask(__name__)
app.secret_key = "spendly-dev-secret"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _parse_date(raw):
    try:
        datetime.strptime(raw, "%Y-%m-%d")
        return raw
    except (ValueError, TypeError):
        return None


def _profile_redirect():
    kwargs = {k: request.args[k] for k in ("date_from", "date_to") if request.args.get(k)}
    return redirect(url_for("profile", **kwargs))


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    if not name:
        flash("Name is required.")
        return render_template("register.html")
    if not email:
        flash("Email is required.")
        return render_template("register.html")
    if len(password) < 8:
        flash("Password must be at least 8 characters.")
        return render_template("register.html")
    if password != confirm:
        flash("Passwords do not match.")
        return render_template("register.html")

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        flash("An account with that email already exists.")
        return render_template("register.html")

    flash("Account created! Please sign in.")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email and password are required.")
        return render_template("login.html")

    user = get_user_by_email(email)

    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.")
        return render_template("login.html")

    session.clear()
    session["user_id"]   = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    date_from = _parse_date(request.args.get("date_from", ""))
    date_to   = _parse_date(request.args.get("date_to", ""))

    user         = get_user_by_id(user_id)
    summary      = get_expense_summary(user_id, date_from=date_from, date_to=date_to)
    expenses     = get_expenses_for_user(user_id, date_from=date_from, date_to=date_to)
    member_since = datetime.strptime(user["created_at"][:10], "%Y-%m-%d").strftime("%B %d, %Y")
    total_spent  = f"{summary['total_spent']:.2f}"

    return render_template(
        "profile.html",
        user=user,
        summary=summary,
        expenses=expenses,
        member_since=member_since,
        total_spent=total_spent,
        date_from=date_from or "",
        date_to=date_to or "",
    )


@app.route("/profile/edit", methods=["POST"])
def profile_edit():
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    name  = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()

    if not name:
        flash("Name is required.")
        return _profile_redirect()
    if not email:
        flash("Email is required.")
        return _profile_redirect()

    try:
        update_user(user_id, name, email)
    except sqlite3.IntegrityError:
        flash("That email address is already in use.")
        return _profile_redirect()

    session["user_name"] = name
    flash("Profile updated successfully.")
    return _profile_redirect()


@app.route("/profile/password", methods=["POST"])
def profile_password():
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    current = request.form.get("current_password", "")
    new_pw  = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    user = get_user_by_id(user_id)

    if not check_password_hash(user["password_hash"], current):
        flash("Current password is incorrect.")
        return _profile_redirect()
    if len(new_pw) < 8:
        flash("New password must be at least 8 characters.")
        return _profile_redirect()
    if new_pw != confirm:
        flash("New passwords do not match.")
        return _profile_redirect()

    update_password(user_id, new_pw)
    flash("Password changed successfully.")
    return _profile_redirect()


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


VALID_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    if request.method == "GET":
        return render_template("add_expense.html", form={})

    amount_raw  = request.form.get("amount", "").strip()
    category    = request.form.get("category", "").strip()
    date_raw    = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    form = {"amount": amount_raw, "category": category,
            "date": date_raw, "description": description}

    try:
        amount = float(amount_raw)
        if amount <= 0 or not math.isfinite(amount):
            raise ValueError
    except (ValueError, TypeError):
        flash("Amount must be a positive number.")
        return render_template("add_expense.html", form=form)

    if category not in VALID_CATEGORIES:
        flash("Please select a valid category.")
        return render_template("add_expense.html", form=form)

    date = _parse_date(date_raw)
    if not date:
        flash("Date must be in YYYY-MM-DD format.")
        return render_template("add_expense.html", form=form)

    create_expense(user_id, amount, category, date, description)
    flash("Expense added successfully.")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    expense = get_expense_by_id(id)
    if expense is None:
        abort(404)
    if expense["user_id"] != user_id:
        abort(403)

    if request.method == "GET":
        return render_template("edit_expense.html", expense=expense, form=dict(expense))

    amount_raw  = request.form.get("amount", "").strip()
    category    = request.form.get("category", "").strip()
    date_raw    = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    form = {"amount": amount_raw, "category": category,
            "date": date_raw, "description": description}

    try:
        amount = float(amount_raw)
        if amount <= 0 or not math.isfinite(amount):
            raise ValueError
    except (ValueError, TypeError):
        flash("Amount must be a positive number.")
        return render_template("edit_expense.html", expense=expense, form=form)

    if category not in VALID_CATEGORIES:
        flash("Please select a valid category.")
        return render_template("edit_expense.html", expense=expense, form=form)

    date = _parse_date(date_raw)
    if not date:
        flash("Date must be in YYYY-MM-DD format.")
        return render_template("edit_expense.html", expense=expense, form=form)

    update_expense(id, amount, category, date, description)
    flash("Expense updated successfully.")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    expense = get_expense_by_id(id)
    if expense is None:
        abort(404)
    if expense["user_id"] != user_id:
        abort(403)

    db_delete_expense(id)
    flash("Expense deleted.")
    return redirect(url_for("profile"))


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, port=port)
