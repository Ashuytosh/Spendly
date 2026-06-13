"""
tests/test_add_expense.py
=========================
Tests for the Add Expense feature (Step 07).

Routes under test:
  GET  /expenses/add  — renders the add-expense form (auth required; 401 if not)
  POST /expenses/add  — validates + inserts, redirects 302 to /profile on success

Validation rules:
  amount      : positive float  — missing / zero / negative / non-numeric all fail
  category    : one of the seven allowed values — missing or unknown string fails
  date        : YYYY-MM-DD      — missing or malformed fails
  description : optional        — blank / absent is fine

On validation failure:
  - Returns 200 (re-renders the form)
  - Shows a flash message
  - Repopulates previously entered field values

On success:
  - Inserts one row into expenses with correct user_id, amount, category, date, description
  - Redirects (302) to /profile
  - Flash success message visible on profile page
"""

import pytest
import database.db as db_module
from app import app as flask_app
from database.db import init_db, seed_db, get_db


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

ADD_URL = "/expenses/add"

VALID_PAYLOAD = {
    "amount": "42.50",
    "category": "Food",
    "date": "2026-06-01",
    "description": "Test lunch",
}


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
    db_file = str(tmp_path / "test_add_expense.db")
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


def _expense_count(app_instance):
    """Return total rows in the expenses table (across all users)."""
    with app_instance.app_context():
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
    return count


def _latest_expense(app_instance):
    """Return the most recently inserted row from the expenses table."""
    with app_instance.app_context():
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses ORDER BY id DESC LIMIT 1"
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
    return row[0]


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_get_returns_401(self, client):
        resp = client.get(ADD_URL)
        assert resp.status_code == 401, (
            "Unauthenticated GET /expenses/add must return 401"
        )

    def test_unauthenticated_post_returns_401(self, client):
        resp = client.post(ADD_URL, data=VALID_PAYLOAD)
        assert resp.status_code == 401, (
            "Unauthenticated POST /expenses/add must return 401"
        )

    def test_unauthenticated_get_does_not_return_200(self, client):
        resp = client.get(ADD_URL)
        assert resp.status_code != 200, (
            "Unauthenticated GET /expenses/add must not succeed with 200"
        )

    def test_unauthenticated_post_does_not_redirect_to_profile(self, client):
        resp = client.post(ADD_URL, data=VALID_PAYLOAD, follow_redirects=False)
        assert resp.status_code != 302, (
            "Unauthenticated POST must not redirect to /profile (must be rejected)"
        )

    def test_unauthenticated_post_inserts_no_row(self, client, app):
        """An unauthenticated POST must not write anything to the DB."""
        before = _expense_count(app)
        client.post(ADD_URL, data=VALID_PAYLOAD)
        after = _expense_count(app)
        assert after == before, (
            "Unauthenticated POST must not insert any row into expenses"
        )


# ------------------------------------------------------------------ #
# GET /expenses/add — authenticated                                   #
# ------------------------------------------------------------------ #

class TestGetForm:
    def test_authenticated_get_returns_200(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert resp.status_code == 200, (
            "Authenticated GET /expenses/add must return 200"
        )

    def test_response_is_html(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert "text/html" in resp.content_type, (
            "GET /expenses/add must return an HTML response"
        )

    def test_form_has_post_method(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert b'method="POST"' in resp.data or b"method='POST'" in resp.data, (
            "The add-expense form must use POST method"
        )

    def test_form_action_points_to_add_expense(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert b"/expenses/add" in resp.data, (
            "Form action must reference the /expenses/add endpoint"
        )

    def test_form_has_amount_input(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert b'name="amount"' in resp.data, (
            "Add-expense form must contain an amount input"
        )

    def test_form_has_category_input(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert b'name="category"' in resp.data, (
            "Add-expense form must contain a category input"
        )

    def test_form_has_date_input(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert b'name="date"' in resp.data, (
            "Add-expense form must contain a date input"
        )

    def test_form_has_description_input(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert b'name="description"' in resp.data, (
            "Add-expense form must contain a description input"
        )

    def test_form_lists_all_seven_categories(self, auth_client):
        resp = auth_client.get(ADD_URL)
        for cat in VALID_CATEGORIES:
            assert cat.encode() in resp.data, (
                f"Category '{cat}' must appear in the add-expense form"
            )

    def test_page_extends_base_template(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert b"<nav" in resp.data or b"navbar" in resp.data, (
            "Add-expense page must extend base.html and include the shared navbar"
        )


# ------------------------------------------------------------------ #
# POST /expenses/add — happy path                                     #
# ------------------------------------------------------------------ #

class TestPostSuccess:
    def test_valid_post_redirects_302(self, auth_client):
        resp = auth_client.post(ADD_URL, data=VALID_PAYLOAD, follow_redirects=False)
        assert resp.status_code == 302, (
            "Valid POST /expenses/add must redirect with 302"
        )

    def test_valid_post_redirects_to_profile(self, auth_client):
        resp = auth_client.post(ADD_URL, data=VALID_PAYLOAD, follow_redirects=False)
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"Valid POST must redirect to /profile, got Location: {location}"
        )

    def test_valid_post_inserts_one_row(self, auth_client, app):
        before = _expense_count(app)
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)
        after = _expense_count(app)
        assert after == before + 1, (
            "Valid POST must insert exactly one row into the expenses table"
        )

    def test_valid_post_stores_correct_amount(self, auth_client, app):
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)
        row = _latest_expense(app)
        assert row["amount"] == pytest.approx(42.50, abs=0.001), (
            "Stored amount must match the submitted value"
        )

    def test_valid_post_stores_correct_category(self, auth_client, app):
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)
        row = _latest_expense(app)
        assert row["category"] == "Food", (
            "Stored category must match the submitted value"
        )

    def test_valid_post_stores_correct_date(self, auth_client, app):
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)
        row = _latest_expense(app)
        assert row["date"] == "2026-06-01", (
            "Stored date must match the submitted YYYY-MM-DD value"
        )

    def test_valid_post_stores_correct_description(self, auth_client, app):
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)
        row = _latest_expense(app)
        assert row["description"] == "Test lunch", (
            "Stored description must match the submitted value"
        )

    def test_valid_post_stores_correct_user_id(self, auth_client, app):
        demo_uid = _get_demo_user_id(app)
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)
        row = _latest_expense(app)
        assert row["user_id"] == demo_uid, (
            "Stored user_id must match the logged-in user's id"
        )

    def test_valid_post_shows_success_flash_on_profile(self, auth_client):
        resp = auth_client.post(ADD_URL, data=VALID_PAYLOAD, follow_redirects=True)
        assert resp.status_code == 200, "Following the redirect must land on a 200 page"
        data_lower = resp.data.lower()
        has_success = (
            b"success" in data_lower
            or b"added" in data_lower
            or b"expense" in data_lower
        )
        assert has_success, (
            "A success flash message must be visible after a valid expense submission"
        )

    def test_valid_post_amount_stored_as_float(self, auth_client, app):
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)
        row = _latest_expense(app)
        assert isinstance(row["amount"], float), (
            "Amount must be stored as a float in the DB"
        )


# ------------------------------------------------------------------ #
# POST — optional description                                         #
# ------------------------------------------------------------------ #

class TestOptionalDescription:
    def test_blank_description_succeeds(self, auth_client, app):
        """A POST with an empty description string must still succeed."""
        payload = {**VALID_PAYLOAD, "description": ""}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 302, (
            "POST with blank description must redirect (succeed)"
        )

    def test_blank_description_inserts_row(self, auth_client, app):
        payload = {**VALID_PAYLOAD, "description": ""}
        before = _expense_count(app)
        auth_client.post(ADD_URL, data=payload)
        after = _expense_count(app)
        assert after == before + 1, (
            "POST with blank description must insert a row into expenses"
        )

    def test_blank_description_stored_as_null_or_empty(self, auth_client, app):
        payload = {**VALID_PAYLOAD, "description": ""}
        auth_client.post(ADD_URL, data=payload)
        row = _latest_expense(app)
        # The spec says description is optional; DB should store NULL or empty string
        assert row["description"] is None or row["description"] == "", (
            "Blank description must be stored as NULL or empty string in the DB"
        )

    def test_missing_description_key_succeeds(self, auth_client, app):
        """POST with no description field at all must also succeed."""
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "description"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 302, (
            "POST without a description field must redirect (succeed)"
        )


# ------------------------------------------------------------------ #
# POST — amount validation                                            #
# ------------------------------------------------------------------ #

class TestAmountValidation:
    def _post_with_amount(self, auth_client, amount_value):
        payload = {**VALID_PAYLOAD, "amount": amount_value}
        return auth_client.post(ADD_URL, data=payload, follow_redirects=False)

    def test_missing_amount_returns_200(self, auth_client):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "amount"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            "Missing amount must re-render the form (200)"
        )

    def test_zero_amount_returns_200(self, auth_client):
        resp = self._post_with_amount(auth_client, "0")
        assert resp.status_code == 200, (
            "Zero amount must re-render the form (200)"
        )

    def test_negative_amount_returns_200(self, auth_client):
        resp = self._post_with_amount(auth_client, "-10.00")
        assert resp.status_code == 200, (
            "Negative amount must re-render the form (200)"
        )

    def test_non_numeric_amount_returns_200(self, auth_client):
        resp = self._post_with_amount(auth_client, "abc")
        assert resp.status_code == 200, (
            "Non-numeric amount must re-render the form (200)"
        )

    def test_empty_amount_string_returns_200(self, auth_client):
        resp = self._post_with_amount(auth_client, "")
        assert resp.status_code == 200, (
            "Empty amount string must re-render the form (200)"
        )

    def test_invalid_amount_shows_flash(self, auth_client):
        resp = self._post_with_amount(auth_client, "-5")
        assert resp.status_code == 200
        # Flash messages appear in the HTML body
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

    def test_invalid_amount_does_not_insert_row(self, auth_client, app):
        before = _expense_count(app)
        self._post_with_amount(auth_client, "0")
        after = _expense_count(app)
        assert after == before, (
            "Invalid amount must not insert any row into expenses"
        )

    @pytest.mark.parametrize("bad_amount", [
        "0", "-1", "-0.01", "abc", "", "   ", "1e999", "NaN", "inf",
    ])
    def test_parametrized_bad_amounts_return_200(self, auth_client, bad_amount):
        payload = {**VALID_PAYLOAD, "amount": bad_amount}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            f"Amount '{bad_amount}' must be rejected and re-render the form"
        )

    @pytest.mark.parametrize("good_amount", [
        "0.01", "1", "100", "9999.99", "0.001",
    ])
    def test_parametrized_valid_amounts_redirect(self, auth_client, good_amount):
        payload = {**VALID_PAYLOAD, "amount": good_amount}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 302, (
            f"Amount '{good_amount}' is valid and must redirect (302)"
        )


# ------------------------------------------------------------------ #
# POST — category validation                                          #
# ------------------------------------------------------------------ #

class TestCategoryValidation:
    def _post_with_category(self, auth_client, category_value):
        payload = {**VALID_PAYLOAD, "category": category_value}
        return auth_client.post(ADD_URL, data=payload, follow_redirects=False)

    def test_missing_category_returns_200(self, auth_client):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "category"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            "Missing category must re-render the form (200)"
        )

    def test_unknown_category_returns_200(self, auth_client):
        resp = self._post_with_category(auth_client, "Vacation")
        assert resp.status_code == 200, (
            "Unknown category 'Vacation' must re-render the form (200)"
        )

    def test_empty_category_string_returns_200(self, auth_client):
        resp = self._post_with_category(auth_client, "")
        assert resp.status_code == 200, (
            "Empty category string must re-render the form (200)"
        )

    def test_invalid_category_shows_flash(self, auth_client):
        resp = self._post_with_category(auth_client, "NotACategory")
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

    def test_invalid_category_does_not_insert_row(self, auth_client, app):
        before = _expense_count(app)
        self._post_with_category(auth_client, "Luxury")
        after = _expense_count(app)
        assert after == before, (
            "Invalid category must not insert any row into expenses"
        )

    @pytest.mark.parametrize("bad_category", [
        "", "Rent", "Travel", "Groceries", "FOOD", "food",
    ])
    def test_parametrized_bad_categories_return_200(self, auth_client, bad_category):
        payload = {**VALID_PAYLOAD, "category": bad_category}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            f"Category '{bad_category}' must be rejected and re-render the form"
        )

    @pytest.mark.parametrize("good_category", VALID_CATEGORIES)
    def test_all_valid_categories_accepted(self, auth_client, good_category):
        payload = {**VALID_PAYLOAD, "category": good_category}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 302, (
            f"Category '{good_category}' is valid and must be accepted (302 redirect)"
        )


# ------------------------------------------------------------------ #
# POST — date validation                                              #
# ------------------------------------------------------------------ #

class TestDateValidation:
    def _post_with_date(self, auth_client, date_value):
        payload = {**VALID_PAYLOAD, "date": date_value}
        return auth_client.post(ADD_URL, data=payload, follow_redirects=False)

    def test_missing_date_returns_200(self, auth_client):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "date"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            "Missing date must re-render the form (200)"
        )

    def test_empty_date_returns_200(self, auth_client):
        resp = self._post_with_date(auth_client, "")
        assert resp.status_code == 200, (
            "Empty date string must re-render the form (200)"
        )

    def test_invalid_date_shows_flash(self, auth_client):
        resp = self._post_with_date(auth_client, "not-a-date")
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

    def test_invalid_date_does_not_insert_row(self, auth_client, app):
        before = _expense_count(app)
        self._post_with_date(auth_client, "13/06/2026")
        after = _expense_count(app)
        assert after == before, (
            "Invalid date must not insert any row into expenses"
        )

    @pytest.mark.parametrize("bad_date", [
        "",
        "not-a-date",
        "06/13/2026",       # MM/DD/YYYY — wrong separator style
        "13-06-2026",       # DD-MM-YYYY — wrong order
        "20260613",         # no separators
        "2026-13-01",       # month 13 doesn't exist
        "2026-00-10",       # month 0 doesn't exist
        "2026-06-32",       # day 32 doesn't exist
        "yesterday",
        "null",
    ])
    def test_parametrized_bad_dates_return_200(self, auth_client, bad_date):
        payload = {**VALID_PAYLOAD, "date": bad_date}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            f"Date '{bad_date}' must be rejected and re-render the form"
        )

    @pytest.mark.parametrize("good_date", [
        "2026-01-01",
        "2026-06-13",
        "2026-12-31",
        "2020-02-29",   # 2020 is a leap year
    ])
    def test_parametrized_valid_dates_redirect(self, auth_client, good_date):
        payload = {**VALID_PAYLOAD, "date": good_date}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 302, (
            f"Date '{good_date}' is valid and must be accepted (302 redirect)"
        )


# ------------------------------------------------------------------ #
# POST — field repopulation on validation failure                     #
# ------------------------------------------------------------------ #

class TestFieldRepopulation:
    def test_amount_repopulated_on_invalid_category(self, auth_client):
        payload = {**VALID_PAYLOAD, "category": "InvalidCategory"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200
        assert b"42.50" in resp.data, (
            "Previously entered amount must be repopulated in the form on validation failure"
        )

    def test_date_repopulated_on_invalid_amount(self, auth_client):
        payload = {**VALID_PAYLOAD, "amount": "-5"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200
        assert b"2026-06-01" in resp.data, (
            "Previously entered date must be repopulated in the form on validation failure"
        )

    def test_description_repopulated_on_invalid_date(self, auth_client):
        payload = {**VALID_PAYLOAD, "date": "not-a-date"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200
        assert b"Test lunch" in resp.data, (
            "Previously entered description must be repopulated in the form on validation failure"
        )

    def test_selected_category_repopulated_on_invalid_amount(self, auth_client):
        payload = {**VALID_PAYLOAD, "amount": "0", "category": "Health"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200
        assert b"Health" in resp.data, (
            "Previously selected category must be present in the re-rendered form"
        )

    def test_amount_repopulated_on_invalid_date(self, auth_client):
        payload = {**VALID_PAYLOAD, "date": "", "amount": "99.99"}
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        assert resp.status_code == 200
        assert b"99.99" in resp.data, (
            "Amount must be preserved when date validation fails"
        )


# ------------------------------------------------------------------ #
# POST — SQL injection safety                                         #
# ------------------------------------------------------------------ #

class TestSQLInjectionSafety:
    def test_sql_injection_in_description_is_stored_safely(self, auth_client, app):
        """
        A SQL injection string in description must be stored verbatim
        (parameterized queries prevent injection; the row IS inserted).
        """
        injection = "'; DROP TABLE expenses; --"
        payload = {**VALID_PAYLOAD, "description": injection}
        before = _expense_count(app)
        auth_client.post(ADD_URL, data=payload)
        after = _expense_count(app)
        # Table must still exist and have gained exactly one row
        assert after == before + 1, (
            "SQL injection in description must not drop the table; row must be inserted"
        )
        row = _latest_expense(app)
        assert row["description"] == injection, (
            "SQL injection string in description must be stored verbatim, not executed"
        )

    def test_sql_injection_in_category_rejected_by_validation(self, auth_client, app):
        """
        A SQL injection string as category is not in the allowed list,
        so validation must reject it without inserting a row.
        """
        injection = "' OR '1'='1"
        payload = {**VALID_PAYLOAD, "category": injection}
        before = _expense_count(app)
        resp = auth_client.post(ADD_URL, data=payload, follow_redirects=False)
        after = _expense_count(app)
        assert resp.status_code == 200, (
            "SQL injection in category must fail validation (200 re-render)"
        )
        assert after == before, (
            "SQL injection in category must not insert any row"
        )


# ------------------------------------------------------------------ #
# POST — cross-user isolation                                         #
# ------------------------------------------------------------------ #

class TestCrossUserIsolation:
    def test_expense_owned_by_submitting_user_not_other(self, auth_client, app):
        """
        Register a second user, log in as demo, add an expense.
        The new row's user_id must be the demo user's id, never the second user's id.
        """
        # Insert a second user directly (auth_client is already logged in, so
        # visiting /register would redirect rather than create the account)
        from database.db import create_user as _create_user
        with app.app_context():
            _create_user("Other User", "other@spendly.com", "otherpass123")
            conn = get_db()
            other_row = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("other@spendly.com",)
            ).fetchone()
            conn.close()
        other_uid = other_row[0]

        # Add an expense as demo user (auth_client is already logged in as demo)
        auth_client.post(ADD_URL, data=VALID_PAYLOAD)

        row = _latest_expense(app)
        demo_uid = _get_demo_user_id(app)

        assert row["user_id"] == demo_uid, (
            "Expense must be owned by the logged-in demo user"
        )
        assert row["user_id"] != other_uid, (
            "Expense must not be attributed to the second user"
        )


# ------------------------------------------------------------------ #
# POST — multiple valid submissions                                   #
# ------------------------------------------------------------------ #

class TestMultipleSubmissions:
    def test_two_valid_submissions_insert_two_rows(self, auth_client, app):
        before = _expense_count(app)

        auth_client.post(
            ADD_URL,
            data={"amount": "10.00", "category": "Food", "date": "2026-06-01", "description": ""},
        )
        auth_client.post(
            ADD_URL,
            data={"amount": "20.00", "category": "Bills", "date": "2026-06-02", "description": ""},
        )

        after = _expense_count(app)
        assert after == before + 2, (
            "Two valid POST submissions must insert two rows into expenses"
        )

    def test_second_row_has_correct_values(self, auth_client, app):
        auth_client.post(
            ADD_URL,
            data={"amount": "10.00", "category": "Food", "date": "2026-06-01", "description": ""},
        )
        auth_client.post(
            ADD_URL,
            data={"amount": "77.77", "category": "Shopping", "date": "2026-07-04", "description": "Sale"},
        )

        row = _latest_expense(app)
        assert row["amount"] == pytest.approx(77.77, abs=0.001)
        assert row["category"] == "Shopping"
        assert row["date"] == "2026-07-04"
        assert row["description"] == "Sale"
