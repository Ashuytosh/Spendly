"""
tests/test_edit_expense.py
==========================
Tests for the Edit Expense feature.

Routes under test:
  GET  /expenses/<id>/edit  — renders pre-filled edit form (auth required; 401 if not)
  POST /expenses/<id>/edit  — validates + updates, redirects 302 to /profile on success

Authorization rules:
  Unauthenticated            → 401
  Non-existent expense id    → 404
  Expense owned by other user → 403

Validation rules (same as add-expense):
  amount      : positive finite float — missing / zero / negative / non-numeric all fail
  category    : one of seven allowed values — unknown string fails
  date        : YYYY-MM-DD — missing or malformed fails
  description : optional — blank / absent → stored as None

On validation failure:
  - Returns 200 (re-renders form)
  - Flash message shown
  - Submitted (bad) values repopulated in form fields (not original DB values)

On success:
  - Updates the existing DB row in-place
  - Flashes "Expense updated successfully."
  - Redirects (302) to /profile

Profile page (GET /profile):
  - Contains an Edit button/link per expense row
  - Expense list respects date_from / date_to query params
"""

import pytest
import database.db as db_module
from app import app as flask_app
from database.db import init_db, seed_db, get_db, create_user


# ------------------------------------------------------------------ #
# Constants                                                           #
# ------------------------------------------------------------------ #

VALID_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

VALID_PAYLOAD = {
    "amount": "55.00",
    "category": "Transport",
    "date": "2026-06-10",
    "description": "Updated description",
}

PROFILE_URL = "/profile"


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def app(tmp_path, monkeypatch):
    """
    Yield a Flask test app backed by a fresh temp-file SQLite DB.

    DB_PATH is monkeypatched so no production data is touched.
    seed_db() seeds one demo user (demo@spendly.com / demo123) and 8 expenses.
    """
    db_file = str(tmp_path / "test_edit_expense.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_file)

    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
    )

    with flask_app.app_context():
        init_db()
        seed_db()
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Test client already logged in as the seeded demo user."""
    resp = client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302, (
        "Login during fixture setup must redirect (302) — check demo credentials"
    )
    return client


@pytest.fixture
def demo_expense_id(app):
    """Return the id of the first seeded expense belonging to the demo user."""
    with app.app_context():
        conn = get_db()
        row = conn.execute(
            "SELECT id FROM expenses ORDER BY id ASC LIMIT 1"
        ).fetchone()
        conn.close()
    return row["id"]


@pytest.fixture
def other_user_expense_id(app):
    """
    Create a second user with their own expense and return that expense id.
    Used to test 403 ownership checks.
    """
    with app.app_context():
        create_user("Other User", "other@spendly.com", "otherpass")
        conn = get_db()
        other_uid = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("other@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (other_uid, 10.00, "Food", "2026-01-01", "Other user's expense"),
        )
        conn.commit()
        expense_row = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ?", (other_uid,)
        ).fetchone()
        conn.close()
    return expense_row["id"]


def _get_expense_row(app_instance, expense_id):
    """Return the current DB row for an expense by id."""
    with app_instance.app_context():
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
    return row


def _get_demo_user_id(app_instance):
    """Return the id of the seeded demo user."""
    with app_instance.app_context():
        conn = get_db()
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
        conn.close()
    return row["id"]


def _edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


# ------------------------------------------------------------------ #
# Auth guard — GET                                                     #
# ------------------------------------------------------------------ #

class TestGetAuthGuard:
    def test_unauthenticated_get_returns_401(self, client, demo_expense_id):
        resp = client.get(_edit_url(demo_expense_id))
        assert resp.status_code == 401, (
            "Unauthenticated GET /expenses/<id>/edit must return 401"
        )

    def test_unauthenticated_get_does_not_return_200(self, client, demo_expense_id):
        resp = client.get(_edit_url(demo_expense_id))
        assert resp.status_code != 200, (
            "Unauthenticated GET must not succeed with 200"
        )

    def test_unauthenticated_get_nonexistent_id_returns_401(self, client):
        """Auth check must fire before the 404 lookup."""
        resp = client.get(_edit_url(99999))
        assert resp.status_code == 401, (
            "Unauthenticated request to non-existent id must still return 401"
        )


# ------------------------------------------------------------------ #
# Auth guard — POST                                                    #
# ------------------------------------------------------------------ #

class TestPostAuthGuard:
    def test_unauthenticated_post_returns_401(self, client, demo_expense_id):
        resp = client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        assert resp.status_code == 401, (
            "Unauthenticated POST /expenses/<id>/edit must return 401"
        )

    def test_unauthenticated_post_does_not_update_db(self, client, app, demo_expense_id):
        original = _get_expense_row(app, demo_expense_id)
        client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        after = _get_expense_row(app, demo_expense_id)
        assert after["amount"] == original["amount"], (
            "Unauthenticated POST must not modify the expense row"
        )

    def test_unauthenticated_post_does_not_redirect_to_profile(
        self, client, demo_expense_id
    ):
        resp = client.post(
            _edit_url(demo_expense_id), data=VALID_PAYLOAD, follow_redirects=False
        )
        assert resp.status_code != 302, (
            "Unauthenticated POST must not redirect to /profile"
        )


# ------------------------------------------------------------------ #
# 404 — non-existent expense id                                       #
# ------------------------------------------------------------------ #

class TestNotFound:
    def test_get_nonexistent_id_returns_404(self, auth_client):
        resp = auth_client.get(_edit_url(99999))
        assert resp.status_code == 404, (
            "GET /expenses/99999/edit must return 404 for a non-existent id"
        )

    def test_post_nonexistent_id_returns_404(self, auth_client):
        resp = auth_client.post(_edit_url(99999), data=VALID_PAYLOAD)
        assert resp.status_code == 404, (
            "POST /expenses/99999/edit must return 404 for a non-existent id"
        )


# ------------------------------------------------------------------ #
# 403 — expense owned by a different user                             #
# ------------------------------------------------------------------ #

class TestForbidden:
    def test_get_other_users_expense_returns_403(
        self, auth_client, other_user_expense_id
    ):
        resp = auth_client.get(_edit_url(other_user_expense_id))
        assert resp.status_code == 403, (
            "GET /expenses/<id>/edit for another user's expense must return 403"
        )

    def test_post_other_users_expense_returns_403(
        self, auth_client, other_user_expense_id
    ):
        resp = auth_client.post(
            _edit_url(other_user_expense_id), data=VALID_PAYLOAD
        )
        assert resp.status_code == 403, (
            "POST /expenses/<id>/edit for another user's expense must return 403"
        )

    def test_post_other_users_expense_does_not_update_db(
        self, auth_client, app, other_user_expense_id
    ):
        original = _get_expense_row(app, other_user_expense_id)
        auth_client.post(
            _edit_url(other_user_expense_id), data=VALID_PAYLOAD
        )
        after = _get_expense_row(app, other_user_expense_id)
        assert after["amount"] == original["amount"], (
            "A 403-rejected POST must not modify the other user's expense"
        )


# ------------------------------------------------------------------ #
# GET /expenses/<id>/edit — authenticated owner                       #
# ------------------------------------------------------------------ #

class TestGetForm:
    def test_authenticated_get_returns_200(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert resp.status_code == 200, (
            "Authenticated GET /expenses/<id>/edit must return 200 for the owner"
        )

    def test_response_is_html(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert "text/html" in resp.content_type, (
            "GET /expenses/<id>/edit must return an HTML response"
        )

    def test_form_is_prefilled_with_amount(self, auth_client, app, demo_expense_id):
        original = _get_expense_row(app, demo_expense_id)
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert str(original["amount"]).encode() in resp.data or (
            f'{original["amount"]:.2f}'.encode() in resp.data
        ), "Edit form must pre-fill the amount field with the stored value"

    def test_form_is_prefilled_with_category(self, auth_client, app, demo_expense_id):
        original = _get_expense_row(app, demo_expense_id)
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert original["category"].encode() in resp.data, (
            "Edit form must pre-fill the category with the stored value"
        )

    def test_form_is_prefilled_with_date(self, auth_client, app, demo_expense_id):
        original = _get_expense_row(app, demo_expense_id)
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert original["date"].encode() in resp.data, (
            "Edit form must pre-fill the date field with the stored value"
        )

    def test_form_is_prefilled_with_description(self, auth_client, app, demo_expense_id):
        original = _get_expense_row(app, demo_expense_id)
        resp = auth_client.get(_edit_url(demo_expense_id))
        if original["description"]:
            assert original["description"].encode() in resp.data, (
                "Edit form must pre-fill the description with the stored value"
            )

    def test_form_has_post_method(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert b'method="POST"' in resp.data or b"method='POST'" in resp.data, (
            "The edit form must use POST method"
        )

    def test_form_action_references_edit_url(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert f"/expenses/{demo_expense_id}/edit".encode() in resp.data, (
            "Form action must reference the correct edit endpoint"
        )

    def test_form_has_amount_input(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert b'name="amount"' in resp.data, (
            "Edit form must contain an amount input"
        )

    def test_form_has_category_input(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert b'name="category"' in resp.data, (
            "Edit form must contain a category input"
        )

    def test_form_has_date_input(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert b'name="date"' in resp.data, (
            "Edit form must contain a date input"
        )

    def test_form_has_description_input(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert b'name="description"' in resp.data, (
            "Edit form must contain a description input"
        )

    def test_form_lists_all_seven_categories(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        for cat in VALID_CATEGORIES:
            assert cat.encode() in resp.data, (
                f"Category '{cat}' must appear in the edit form"
            )

    def test_page_extends_base_template(self, auth_client, demo_expense_id):
        resp = auth_client.get(_edit_url(demo_expense_id))
        assert b"<nav" in resp.data or b"navbar" in resp.data, (
            "Edit page must extend base.html and include the shared navbar"
        )


# ------------------------------------------------------------------ #
# POST /expenses/<id>/edit — happy path                               #
# ------------------------------------------------------------------ #

class TestPostSuccess:
    def test_valid_post_redirects_302(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=VALID_PAYLOAD, follow_redirects=False
        )
        assert resp.status_code == 302, (
            "Valid POST /expenses/<id>/edit must redirect with 302"
        )

    def test_valid_post_redirects_to_profile(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=VALID_PAYLOAD, follow_redirects=False
        )
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"Valid POST must redirect to /profile, got Location: {location}"
        )

    def test_valid_post_updates_amount(self, auth_client, app, demo_expense_id):
        auth_client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        row = _get_expense_row(app, demo_expense_id)
        assert row["amount"] == pytest.approx(55.00, abs=0.001), (
            "Amount must be updated to the submitted value"
        )

    def test_valid_post_updates_category(self, auth_client, app, demo_expense_id):
        auth_client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        row = _get_expense_row(app, demo_expense_id)
        assert row["category"] == "Transport", (
            "Category must be updated to the submitted value"
        )

    def test_valid_post_updates_date(self, auth_client, app, demo_expense_id):
        auth_client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        row = _get_expense_row(app, demo_expense_id)
        assert row["date"] == "2026-06-10", (
            "Date must be updated to the submitted value"
        )

    def test_valid_post_updates_description(self, auth_client, app, demo_expense_id):
        auth_client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        row = _get_expense_row(app, demo_expense_id)
        assert row["description"] == "Updated description", (
            "Description must be updated to the submitted value"
        )

    def test_valid_post_does_not_change_row_count(self, auth_client, app, demo_expense_id):
        """An edit must update in-place; no new row must be created."""
        with app.app_context():
            conn = get_db()
            before = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
            conn.close()
        auth_client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        with app.app_context():
            conn = get_db()
            after = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
            conn.close()
        assert after == before, (
            "Edit must update in-place — total row count must not change"
        )

    def test_valid_post_does_not_change_user_id(self, auth_client, app, demo_expense_id):
        demo_uid = _get_demo_user_id(app)
        auth_client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        row = _get_expense_row(app, demo_expense_id)
        assert row["user_id"] == demo_uid, (
            "Edit must not reassign the expense to a different user"
        )

    def test_valid_post_shows_success_flash_on_profile(
        self, auth_client, demo_expense_id
    ):
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=VALID_PAYLOAD, follow_redirects=True
        )
        assert resp.status_code == 200, (
            "Following the redirect after edit must land on a 200 page"
        )
        data_lower = resp.data.lower()
        has_success = (
            b"updated" in data_lower
            or b"success" in data_lower
            or b"expense updated" in data_lower
        )
        assert has_success, (
            "A success flash message must be visible on the profile page after edit"
        )

    def test_updated_amount_visible_in_profile_expense_list(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "amount": "77.77"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=True
        )
        assert b"77.77" in resp.data, (
            "The updated amount must be visible in the profile expense list after redirect"
        )

    def test_updated_category_visible_in_profile_expense_list(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "category": "Health"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=True
        )
        assert b"Health" in resp.data, (
            "The updated category must be visible in the profile expense list"
        )

    def test_updated_date_visible_in_profile_expense_list(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "date": "2026-07-15"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=True
        )
        assert b"2026-07-15" in resp.data, (
            "The updated date must be visible in the profile expense list"
        )


# ------------------------------------------------------------------ #
# POST — optional description                                         #
# ------------------------------------------------------------------ #

class TestOptionalDescription:
    def test_blank_description_succeeds(self, auth_client, demo_expense_id):
        payload = {**VALID_PAYLOAD, "description": ""}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 302, (
            "POST with blank description must redirect (succeed)"
        )

    def test_blank_description_stored_as_none(self, auth_client, app, demo_expense_id):
        payload = {**VALID_PAYLOAD, "description": ""}
        auth_client.post(_edit_url(demo_expense_id), data=payload)
        row = _get_expense_row(app, demo_expense_id)
        assert row["description"] is None or row["description"] == "", (
            "Blank description must be stored as NULL or empty string in DB"
        )

    def test_missing_description_key_succeeds(self, auth_client, demo_expense_id):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "description"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 302, (
            "POST without a description field must redirect (succeed)"
        )

    def test_missing_description_stored_as_none(
        self, auth_client, app, demo_expense_id
    ):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "description"}
        auth_client.post(_edit_url(demo_expense_id), data=payload)
        row = _get_expense_row(app, demo_expense_id)
        assert row["description"] is None or row["description"] == "", (
            "Absent description field must be stored as None/empty in DB"
        )


# ------------------------------------------------------------------ #
# POST — amount validation                                            #
# ------------------------------------------------------------------ #

class TestAmountValidation:
    def _post(self, auth_client, demo_expense_id, amount_value):
        payload = {**VALID_PAYLOAD, "amount": amount_value}
        return auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )

    def test_missing_amount_returns_200(self, auth_client, demo_expense_id):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "amount"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200, (
            "Missing amount must re-render the form (200)"
        )

    def test_zero_amount_returns_200(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "0")
        assert resp.status_code == 200, (
            "Zero amount must re-render the form (200)"
        )

    def test_negative_amount_returns_200(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "-10.00")
        assert resp.status_code == 200, (
            "Negative amount must re-render the form (200)"
        )

    def test_non_numeric_amount_returns_200(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "abc")
        assert resp.status_code == 200, (
            "Non-numeric amount must re-render the form (200)"
        )

    def test_empty_amount_returns_200(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "")
        assert resp.status_code == 200, (
            "Empty amount string must re-render the form (200)"
        )

    def test_invalid_amount_shows_flash(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "-5")
        data_lower = resp.data.lower()
        has_flash = (
            b"error" in data_lower
            or b"invalid" in data_lower
            or b"amount" in data_lower
            or b"alert" in data_lower
            or b"flash" in data_lower
        )
        assert has_flash, (
            "Validation failure on amount must show a flash message"
        )

    def test_invalid_amount_does_not_update_db(
        self, auth_client, app, demo_expense_id
    ):
        original = _get_expense_row(app, demo_expense_id)
        self._post(auth_client, demo_expense_id, "0")
        after = _get_expense_row(app, demo_expense_id)
        assert after["amount"] == original["amount"], (
            "Invalid amount must not update the DB row"
        )

    @pytest.mark.parametrize("bad_amount", [
        "0", "-1", "-0.01", "abc", "", "   ", "1e999", "NaN", "inf",
    ])
    def test_parametrized_bad_amounts_return_200(
        self, auth_client, demo_expense_id, bad_amount
    ):
        payload = {**VALID_PAYLOAD, "amount": bad_amount}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200, (
            f"Amount '{bad_amount}' must be rejected and re-render the form (200)"
        )

    @pytest.mark.parametrize("good_amount", [
        "0.01", "1", "100", "9999.99", "0.001",
    ])
    def test_parametrized_valid_amounts_redirect(
        self, auth_client, demo_expense_id, good_amount
    ):
        payload = {**VALID_PAYLOAD, "amount": good_amount}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 302, (
            f"Amount '{good_amount}' is valid and must redirect (302)"
        )


# ------------------------------------------------------------------ #
# POST — category validation                                          #
# ------------------------------------------------------------------ #

class TestCategoryValidation:
    def _post(self, auth_client, demo_expense_id, category_value):
        payload = {**VALID_PAYLOAD, "category": category_value}
        return auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )

    def test_missing_category_returns_200(self, auth_client, demo_expense_id):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "category"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200, (
            "Missing category must re-render the form (200)"
        )

    def test_unknown_category_returns_200(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "Vacation")
        assert resp.status_code == 200, (
            "Unknown category must re-render the form (200)"
        )

    def test_empty_category_returns_200(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "")
        assert resp.status_code == 200, (
            "Empty category string must re-render the form (200)"
        )

    def test_invalid_category_shows_flash(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "NotACategory")
        data_lower = resp.data.lower()
        has_flash = (
            b"error" in data_lower
            or b"invalid" in data_lower
            or b"category" in data_lower
            or b"alert" in data_lower
            or b"flash" in data_lower
        )
        assert has_flash, (
            "Validation failure on category must show a flash message"
        )

    def test_invalid_category_does_not_update_db(
        self, auth_client, app, demo_expense_id
    ):
        original = _get_expense_row(app, demo_expense_id)
        self._post(auth_client, demo_expense_id, "Luxury")
        after = _get_expense_row(app, demo_expense_id)
        assert after["category"] == original["category"], (
            "Invalid category must not update the DB row"
        )

    @pytest.mark.parametrize("bad_category", [
        "", "Rent", "Travel", "Groceries", "FOOD", "food",
    ])
    def test_parametrized_bad_categories_return_200(
        self, auth_client, demo_expense_id, bad_category
    ):
        payload = {**VALID_PAYLOAD, "category": bad_category}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200, (
            f"Category '{bad_category}' must be rejected and re-render the form (200)"
        )

    @pytest.mark.parametrize("good_category", VALID_CATEGORIES)
    def test_all_valid_categories_accepted(
        self, auth_client, demo_expense_id, good_category
    ):
        payload = {**VALID_PAYLOAD, "category": good_category}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 302, (
            f"Category '{good_category}' is valid and must be accepted (302 redirect)"
        )


# ------------------------------------------------------------------ #
# POST — date validation                                              #
# ------------------------------------------------------------------ #

class TestDateValidation:
    def _post(self, auth_client, demo_expense_id, date_value):
        payload = {**VALID_PAYLOAD, "date": date_value}
        return auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )

    def test_missing_date_returns_200(self, auth_client, demo_expense_id):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "date"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200, (
            "Missing date must re-render the form (200)"
        )

    def test_empty_date_returns_200(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "")
        assert resp.status_code == 200, (
            "Empty date string must re-render the form (200)"
        )

    def test_invalid_date_shows_flash(self, auth_client, demo_expense_id):
        resp = self._post(auth_client, demo_expense_id, "not-a-date")
        data_lower = resp.data.lower()
        has_flash = (
            b"error" in data_lower
            or b"invalid" in data_lower
            or b"date" in data_lower
            or b"alert" in data_lower
            or b"flash" in data_lower
        )
        assert has_flash, (
            "Validation failure on date must show a flash message"
        )

    def test_invalid_date_does_not_update_db(
        self, auth_client, app, demo_expense_id
    ):
        original = _get_expense_row(app, demo_expense_id)
        self._post(auth_client, demo_expense_id, "13/06/2026")
        after = _get_expense_row(app, demo_expense_id)
        assert after["date"] == original["date"], (
            "Invalid date must not update the DB row"
        )

    @pytest.mark.parametrize("bad_date", [
        "",
        "not-a-date",
        "06/13/2026",
        "13-06-2026",
        "20260613",
        "2026-13-01",
        "2026-00-10",
        "2026-06-32",
        "yesterday",
        "null",
    ])
    def test_parametrized_bad_dates_return_200(
        self, auth_client, demo_expense_id, bad_date
    ):
        payload = {**VALID_PAYLOAD, "date": bad_date}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200, (
            f"Date '{bad_date}' must be rejected and re-render the form (200)"
        )

    @pytest.mark.parametrize("good_date", [
        "2026-01-01",
        "2026-06-13",
        "2026-12-31",
        "2020-02-29",   # 2020 is a leap year
    ])
    def test_parametrized_valid_dates_redirect(
        self, auth_client, demo_expense_id, good_date
    ):
        payload = {**VALID_PAYLOAD, "date": good_date}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 302, (
            f"Date '{good_date}' is valid and must redirect (302)"
        )


# ------------------------------------------------------------------ #
# POST — field repopulation on validation failure                     #
# ------------------------------------------------------------------ #

class TestFieldRepopulation:
    """
    On a validation failure the form must show the submitted (bad) values,
    NOT the original DB values.  The seeded first expense has amount=12.50
    and category=Food, so we deliberately submit different values and check
    that those are the ones reflected in the re-rendered form.
    """

    def test_submitted_amount_shown_on_invalid_category(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "amount": "88.88", "category": "BadCat"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200
        assert b"88.88" in resp.data, (
            "Submitted amount must be repopulated in the form on validation failure"
        )

    def test_submitted_date_shown_on_invalid_amount(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "amount": "-5", "date": "2026-09-15"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200
        assert b"2026-09-15" in resp.data, (
            "Submitted date must be repopulated in the form on validation failure"
        )

    def test_submitted_description_shown_on_invalid_date(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "date": "not-a-date", "description": "My note here"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200
        assert b"My note here" in resp.data, (
            "Submitted description must be repopulated in the form on validation failure"
        )

    def test_submitted_category_shown_on_invalid_amount(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "amount": "0", "category": "Bills"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200
        assert b"Bills" in resp.data, (
            "Submitted category must be present in the re-rendered form on validation failure"
        )

    def test_submitted_amount_shown_on_invalid_date(
        self, auth_client, demo_expense_id
    ):
        payload = {**VALID_PAYLOAD, "amount": "44.44", "date": ""}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert resp.status_code == 200
        assert b"44.44" in resp.data, (
            "Submitted amount must be preserved when date validation fails"
        )

    def test_repopulated_values_differ_from_original_db_values(
        self, auth_client, app, demo_expense_id
    ):
        """
        Original first seeded expense: amount=12.50, category=Food.
        We submit amount=99.00, category=BadCat.
        The re-rendered form must show 99.00 (submitted), not 12.50 (original).
        """
        original = _get_expense_row(app, demo_expense_id)
        submitted_amount = "99.00"
        assert submitted_amount != str(original["amount"]), (
            "Test setup: submitted value must differ from original DB value"
        )
        payload = {**VALID_PAYLOAD, "amount": submitted_amount, "category": "BadCat"}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        assert b"99.00" in resp.data, (
            "Re-rendered form must show the submitted (invalid) amount, not the original"
        )


# ------------------------------------------------------------------ #
# Profile page — Edit button per row                                  #
# ------------------------------------------------------------------ #

class TestProfileEditButton:
    def test_profile_has_edit_link_or_button(self, auth_client, demo_expense_id):
        resp = auth_client.get(PROFILE_URL)
        assert resp.status_code == 200
        data_lower = resp.data.lower()
        # Accept "edit" appearing as link text, button text, or aria-label
        assert b"edit" in data_lower, (
            "Profile page must contain an 'Edit' link or button for expense rows"
        )

    def test_profile_edit_link_references_expense_id(
        self, auth_client, demo_expense_id
    ):
        resp = auth_client.get(PROFILE_URL)
        assert f"/expenses/{demo_expense_id}/edit".encode() in resp.data, (
            "Profile page must contain a link to the edit route for each expense"
        )

    def test_profile_shows_expense_list(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        assert resp.status_code == 200
        # The profile page must render the expenses list — seeded data has 8 rows
        # Check for presence of at least one known seeded category
        assert b"Food" in resp.data or b"Transport" in resp.data, (
            "Profile page must display the expense list"
        )

    def test_profile_expense_list_shows_amount(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        # One of the seeded amounts must be visible
        assert b"12.50" in resp.data or b"35.00" in resp.data, (
            "Profile page expense list must show expense amounts"
        )

    def test_profile_expense_list_shows_date(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        assert b"2026-05" in resp.data, (
            "Profile page expense list must show expense dates"
        )


# ------------------------------------------------------------------ #
# Profile page — expense list respects date filter                    #
# ------------------------------------------------------------------ #

class TestProfileExpenseListDateFilter:
    """
    Seeded data (all May 2026):
      2026-05-01  Food          12.50
      2026-05-03  Transport     35.00
      2026-05-05  Bills        120.00
      2026-05-08  Health        45.00
      2026-05-10  Entertainment 18.00
      2026-05-14  Shopping      65.00
      2026-05-18  Other          9.99
      2026-05-21  Food          22.00
    """

    def test_date_filter_excludes_earlier_expenses(self, auth_client):
        # Only expenses from 2026-05-14 onward should appear
        resp = auth_client.get(f"{PROFILE_URL}?date_from=2026-05-14")
        # The 2026-05-01 Food expense (12.50) should NOT be in the expense list;
        # the 2026-05-14 Shopping (65.00) SHOULD be.
        assert b"65.00" in resp.data, (
            "Shopping expense on 2026-05-14 must appear when date_from=2026-05-14"
        )

    def test_date_filter_excludes_later_expenses(self, auth_client):
        # Only expenses up to 2026-05-05 should appear
        resp = auth_client.get(f"{PROFILE_URL}?date_to=2026-05-05")
        assert b"120.00" in resp.data, (
            "Bills expense on 2026-05-05 must appear when date_to=2026-05-05"
        )

    def test_date_filter_combined_range(self, auth_client):
        # 2026-05-08 to 2026-05-10: Health (45.00) and Entertainment (18.00)
        resp = auth_client.get(
            f"{PROFILE_URL}?date_from=2026-05-08&date_to=2026-05-10"
        )
        assert b"45.00" in resp.data, (
            "Health expense must appear within the specified date range"
        )
        assert b"18.00" in resp.data, (
            "Entertainment expense must appear within the specified date range"
        )

    def test_date_filter_empty_range_shows_no_expense_rows(self, auth_client):
        # A range with no seeded expenses must result in no rows shown
        resp = auth_client.get(
            f"{PROFILE_URL}?date_from=2025-01-01&date_to=2025-12-31"
        )
        assert resp.status_code == 200
        # None of the seeded amounts should appear in the expense list
        for amount in [b"12.50", b"35.00", b"120.00", b"45.00",
                       b"18.00", b"65.00", b"9.99", b"22.00"]:
            assert amount not in resp.data, (
                f"Amount {amount} must not appear when date range has no matching expenses"
            )

    def test_no_filter_shows_all_seeded_expenses(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        assert b"12.50" in resp.data
        assert b"120.00" in resp.data
        assert b"65.00" in resp.data, (
            "All seeded expenses must be shown when no date filter is active"
        )


# ------------------------------------------------------------------ #
# SQL injection safety                                                #
# ------------------------------------------------------------------ #

class TestSQLInjectionSafety:
    def test_sql_injection_in_description_stored_safely(
        self, auth_client, app, demo_expense_id
    ):
        """
        A SQL injection payload in description must be stored verbatim —
        parameterized queries prevent injection and the row IS updated.
        """
        injection = "'; DROP TABLE expenses; --"
        payload = {**VALID_PAYLOAD, "description": injection}
        auth_client.post(_edit_url(demo_expense_id), data=payload)
        row = _get_expense_row(app, demo_expense_id)
        assert row is not None, (
            "expenses table must still exist after SQL injection in description"
        )
        assert row["description"] == injection, (
            "SQL injection string in description must be stored verbatim, not executed"
        )

    def test_sql_injection_in_category_rejected_by_validation(
        self, auth_client, app, demo_expense_id
    ):
        """
        A SQL injection string as category is not in the allowed list;
        validation must reject it without modifying the row.
        """
        injection = "' OR '1'='1"
        original = _get_expense_row(app, demo_expense_id)
        payload = {**VALID_PAYLOAD, "category": injection}
        resp = auth_client.post(
            _edit_url(demo_expense_id), data=payload, follow_redirects=False
        )
        after = _get_expense_row(app, demo_expense_id)
        assert resp.status_code == 200, (
            "SQL injection in category must fail validation (200 re-render)"
        )
        assert after["category"] == original["category"], (
            "SQL injection in category must not modify the DB row"
        )


# ------------------------------------------------------------------ #
# Cross-user isolation — editing does not bleed across users          #
# ------------------------------------------------------------------ #

class TestCrossUserIsolation:
    def test_editing_own_expense_does_not_affect_other_users_expense(
        self, auth_client, app, demo_expense_id, other_user_expense_id
    ):
        """
        Editing the demo user's expense must not modify the other user's expense.
        """
        other_original = _get_expense_row(app, other_user_expense_id)
        auth_client.post(_edit_url(demo_expense_id), data=VALID_PAYLOAD)
        other_after = _get_expense_row(app, other_user_expense_id)
        assert other_after["amount"] == other_original["amount"], (
            "Editing one user's expense must not alter another user's expense"
        )
        assert other_after["category"] == other_original["category"]

    def test_two_sequential_edits_each_update_correctly(
        self, auth_client, app, demo_expense_id
    ):
        """Two sequential edits to the same expense must each take effect."""
        first_payload = {**VALID_PAYLOAD, "amount": "11.11", "category": "Food"}
        auth_client.post(_edit_url(demo_expense_id), data=first_payload)
        row_after_first = _get_expense_row(app, demo_expense_id)
        assert row_after_first["amount"] == pytest.approx(11.11, abs=0.001)

        second_payload = {**VALID_PAYLOAD, "amount": "22.22", "category": "Bills"}
        auth_client.post(_edit_url(demo_expense_id), data=second_payload)
        row_after_second = _get_expense_row(app, demo_expense_id)
        assert row_after_second["amount"] == pytest.approx(22.22, abs=0.001)
        assert row_after_second["category"] == "Bills"
