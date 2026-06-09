import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session
from werkzeug.security import check_password_hash
from database.db import (
    get_db, init_db, seed_db,
    create_user, get_user_by_email, get_user_by_id,
    get_expense_summary, update_user, update_password,
)

app = Flask(__name__)
app.secret_key = "spendly-dev-secret"

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

    user         = get_user_by_id(user_id)
    summary      = get_expense_summary(user_id)
    member_since = datetime.strptime(user["created_at"][:10], "%Y-%m-%d").strftime("%B %d, %Y")
    total_spent  = f"{summary['total_spent']:.2f}"

    return render_template(
        "profile.html",
        user=user,
        summary=summary,
        member_since=member_since,
        total_spent=total_spent,
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
        return redirect(url_for("profile"))
    if not email:
        flash("Email is required.")
        return redirect(url_for("profile"))

    try:
        update_user(user_id, name, email)
    except sqlite3.IntegrityError:
        flash("That email address is already in use.")
        return redirect(url_for("profile"))

    session["user_name"] = name
    flash("Profile updated successfully.")
    return redirect(url_for("profile"))


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
        return redirect(url_for("profile"))
    if len(new_pw) < 8:
        flash("New password must be at least 8 characters.")
        return redirect(url_for("profile"))
    if new_pw != confirm:
        flash("New passwords do not match.")
        return redirect(url_for("profile"))

    update_password(user_id, new_pw)
    flash("Password changed successfully.")
    return redirect(url_for("profile"))


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
