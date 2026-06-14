"""
tests/test_delete_expense.py
============================
Tests for the Delete Expense feature (Step 09).

Route under test:
  POST /expenses/<int:id>/delete

Authorization rules:
  Unauthenticated              -> 401  (auth fires before any DB lookup)
  Non-existent expense id      -> 404
  Expense owned by other user  -> 403

On success:
  - Deletes the expense row from the DB (verified via get_expense_by_id)
  - Flashes "Expense deleted."
  - Redirects (302) to /profile

Template change:
  profile.html renders an inline <form method="POST" action="/expenses/<id>/delete">
  with a submit button of class "btn-delete" and title "Delete expense".

DB helper added:
  delete_expense(expense_id) in database/db.py issues a parameterized
  DELETE FROM expenses WHERE id = ?
"""

import pytest
import database.db as db_module
from app import app as flask_app
from database.db import (
    init_db,
    seed_db,
    get_db,
    create_user,
    get_expense_by_id,
)


# ------------------------------------------------------------------ #
# URL helpers                                                         #
# ------------------------------------------------------------------ #

PROFILE_URL = "/profile"


def _delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def app(tmp_path, monkeypatch):
    """
    Yield a Flask test app backed by a fresh temp-file SQLite DB.

    DB_PATH is monkeypatched so no production data is ever touched.
    seed_db() seeds one demo user (demo@spendly.com / demo123) and 8 expenses.
    """
    db_file = str(tmp_path / "test_delete_expense.db")
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
def all_demo_expense_ids(app):
    """Return all expense ids seeded for the demo user, ordered ascending."""
    with app.app_context():
        conn = get_db()
        rows = conn.execute(
            "SELECT id FROM expenses ORDER BY id ASC"
        ).fetchall()
        conn.close()
    return [row["id"] for row in rows]


@pytest.fixture
def other_user_expense_id(app):
    """
    Create a second user with their own expense and return that expense's id.
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
            (other_uid, 10.00, "Food", "2026-01-01", "Other user expense"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ?", (other_uid,)
        ).fetchone()
        conn.close()
    return row["id"]


def _expense_count(app_instance):
    """Return total rows in the expenses table (across all users)."""
    with app_instance.app_context():
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
    return count


def _fetch_expense(app_instance, expense_id):
    """Return the DB row for an expense by id, or None if deleted."""
    with app_instance.app_context():
        return get_expense_by_id(expense_id)


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_post_returns_401(self, client, demo_expense_id):
        resp = client.post(_delete_url(demo_expense_id))
        assert resp.status_code == 401, (
            "Unauthenticated POST /expenses/<id>/delete must return 401"
        )

    def test_unauthenticated_post_does_not_return_200(self, client, demo_expense_id):
        resp = client.post(_delete_url(demo_expense_id))
        assert resp.status_code != 200, (
            "Unauthenticated POST must not succeed with 200"
        )

    def test_unauthenticated_post_does_not_redirect_to_profile(
        self, client, demo_expense_id
    ):
        resp = client.post(_delete_url(demo_expense_id), follow_redirects=False)
        assert resp.status_code != 302, (
            "Unauthenticated POST must not issue a 302 redirect"
        )

    def test_unauthenticated_post_does_not_delete_row(
        self, client, app, demo_expense_id
    ):
        client.post(_delete_url(demo_expense_id))
        row = _fetch_expense(app, demo_expense_id)
        assert row is not None, (
            "Unauthenticated POST must not delete the expense row from the DB"
        )

    def test_auth_check_fires_before_404_lookup(self, client):
        """
        Auth guard must fire before the existence check.
        A nonexistent id submitted without a session must still return 401, not 404.
        """
        resp = client.post(_delete_url(99999))
        assert resp.status_code == 401, (
            "Unauthenticated POST to a nonexistent id must return 401, not 404"
        )


# ------------------------------------------------------------------ #
# 404 — non-existent expense id                                       #
# ------------------------------------------------------------------ #

class TestNotFound:
    def test_post_nonexistent_id_returns_404(self, auth_client):
        resp = auth_client.post(_delete_url(99999))
        assert resp.status_code == 404, (
            "POST /expenses/99999/delete must return 404 for a non-existent id"
        )

    def test_post_nonexistent_id_does_not_alter_row_count(self, auth_client, app):
        before = _expense_count(app)
        auth_client.post(_delete_url(99999))
        after = _expense_count(app)
        assert after == before, (
            "A 404-rejected delete must not change the total expense row count"
        )


# ------------------------------------------------------------------ #
# 403 — expense owned by a different user                             #
# ------------------------------------------------------------------ #

class TestForbidden:
    def test_post_other_users_expense_returns_403(
        self, auth_client, other_user_expense_id
    ):
        resp = auth_client.post(_delete_url(other_user_expense_id))
        assert resp.status_code == 403, (
            "POST /expenses/<id>/delete for another user's expense must return 403"
        )

    def test_post_other_users_expense_does_not_delete_row(
        self, auth_client, app, other_user_expense_id
    ):
        auth_client.post(_delete_url(other_user_expense_id))
        row = _fetch_expense(app, other_user_expense_id)
        assert row is not None, (
            "A 403-rejected delete must not remove the other user's expense from the DB"
        )

    def test_post_other_users_expense_does_not_alter_demo_expenses(
        self, auth_client, app, other_user_expense_id, all_demo_expense_ids
    ):
        before_count = _expense_count(app)
        auth_client.post(_delete_url(other_user_expense_id))
        after_count = _expense_count(app)
        assert after_count == before_count, (
            "A 403-rejected delete must not change any expense row counts"
        )


# ------------------------------------------------------------------ #
# Successful DELETE — happy path                                      #
# ------------------------------------------------------------------ #

class TestDeleteSuccess:
    def test_valid_delete_returns_302(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            _delete_url(demo_expense_id), follow_redirects=False
        )
        assert resp.status_code == 302, (
            "Successful DELETE must redirect with 302"
        )

    def test_valid_delete_redirects_to_profile(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            _delete_url(demo_expense_id), follow_redirects=False
        )
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"Successful DELETE must redirect to /profile, got Location: {location}"
        )

    def test_valid_delete_shows_flash_message(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            _delete_url(demo_expense_id), follow_redirects=True
        )
        assert resp.status_code == 200, (
            "Following the redirect after delete must land on a 200 page"
        )
        assert b"Expense deleted." in resp.data, (
            "Flash message 'Expense deleted.' must appear on the profile page after deletion"
        )

    def test_valid_delete_removes_row_from_db(self, auth_client, app, demo_expense_id):
        auth_client.post(_delete_url(demo_expense_id))
        row = _fetch_expense(app, demo_expense_id)
        assert row is None, (
            "After a successful delete, get_expense_by_id must return None for the deleted id"
        )

    def test_valid_delete_decrements_row_count_by_one(
        self, auth_client, app, demo_expense_id
    ):
        before = _expense_count(app)
        auth_client.post(_delete_url(demo_expense_id))
        after = _expense_count(app)
        assert after == before - 1, (
            "Successful delete must reduce the total expense row count by exactly 1"
        )

    def test_valid_delete_lands_on_profile_page(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            _delete_url(demo_expense_id), follow_redirects=True
        )
        # Profile page has the user's name and/or expense list
        assert resp.status_code == 200, (
            "Following the delete redirect must yield a 200 profile page"
        )
        assert b"text/html" in resp.content_type.encode() or "text/html" in resp.content_type, (
            "The response after following the redirect must be an HTML page"
        )

    def test_valid_delete_does_not_remove_other_demo_expenses(
        self, auth_client, app, demo_expense_id, all_demo_expense_ids
    ):
        """Deleting one expense must leave all other expense rows intact."""
        remaining_ids = [eid for eid in all_demo_expense_ids if eid != demo_expense_id]
        auth_client.post(_delete_url(demo_expense_id))
        for eid in remaining_ids:
            row = _fetch_expense(app, eid)
            assert row is not None, (
                f"Expense id={eid} must still exist after a different expense was deleted"
            )

    def test_valid_delete_does_not_affect_other_users_expenses(
        self, auth_client, app, demo_expense_id, other_user_expense_id
    ):
        auth_client.post(_delete_url(demo_expense_id))
        other_row = _fetch_expense(app, other_user_expense_id)
        assert other_row is not None, (
            "Deleting own expense must not remove another user's expense"
        )


# ------------------------------------------------------------------ #
# Idempotency — double delete                                         #
# ------------------------------------------------------------------ #

class TestDoubleDelete:
    def test_second_delete_of_same_id_returns_404(
        self, auth_client, demo_expense_id
    ):
        """
        Once an expense has been deleted, a second POST to the same id
        must return 404 because the row no longer exists.
        """
        auth_client.post(_delete_url(demo_expense_id))
        resp = auth_client.post(_delete_url(demo_expense_id))
        assert resp.status_code == 404, (
            "A second POST to an already-deleted expense id must return 404"
        )

    def test_double_delete_does_not_change_row_count_further(
        self, auth_client, app, demo_expense_id
    ):
        auth_client.post(_delete_url(demo_expense_id))
        count_after_first = _expense_count(app)
        auth_client.post(_delete_url(demo_expense_id))
        count_after_second = _expense_count(app)
        assert count_after_second == count_after_first, (
            "A second (rejected) delete must not change the row count further"
        )


# ------------------------------------------------------------------ #
# Multiple sequential deletes                                         #
# ------------------------------------------------------------------ #

class TestSequentialDeletes:
    def test_two_sequential_deletes_each_remove_one_row(
        self, auth_client, app, all_demo_expense_ids
    ):
        """Deleting two distinct expenses must reduce the count by 2."""
        before = _expense_count(app)
        first_id, second_id = all_demo_expense_ids[0], all_demo_expense_ids[1]
        auth_client.post(_delete_url(first_id))
        auth_client.post(_delete_url(second_id))
        after = _expense_count(app)
        assert after == before - 2, (
            "Two sequential successful deletes must reduce the total count by 2"
        )

    def test_two_sequential_deletes_both_rows_gone(
        self, auth_client, app, all_demo_expense_ids
    ):
        first_id, second_id = all_demo_expense_ids[0], all_demo_expense_ids[1]
        auth_client.post(_delete_url(first_id))
        auth_client.post(_delete_url(second_id))
        assert _fetch_expense(app, first_id) is None, (
            "First deleted expense must not exist in DB"
        )
        assert _fetch_expense(app, second_id) is None, (
            "Second deleted expense must not exist in DB"
        )

    def test_two_sequential_deletes_remaining_rows_intact(
        self, auth_client, app, all_demo_expense_ids
    ):
        first_id, second_id = all_demo_expense_ids[0], all_demo_expense_ids[1]
        surviving_ids = all_demo_expense_ids[2:]
        auth_client.post(_delete_url(first_id))
        auth_client.post(_delete_url(second_id))
        for eid in surviving_ids:
            row = _fetch_expense(app, eid)
            assert row is not None, (
                f"Expense id={eid} must still exist after the two preceding deletes"
            )


# ------------------------------------------------------------------ #
# Profile page — delete form in HTML                                  #
# ------------------------------------------------------------------ #

class TestProfileDeleteForm:
    def test_profile_contains_btn_delete_class(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        assert resp.status_code == 200, (
            "GET /profile must return 200 for an authenticated user"
        )
        assert b"btn-delete" in resp.data, (
            "profile.html must render a submit button with class 'btn-delete' "
            "for each expense row"
        )

    def test_profile_delete_form_has_post_method(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        # The delete form must explicitly use POST (not the default GET)
        assert b'method="POST"' in resp.data or b"method='POST'" in resp.data, (
            "The inline delete form in profile.html must use method=\"POST\""
        )

    def test_profile_delete_form_action_contains_delete_url(
        self, auth_client, demo_expense_id
    ):
        resp = auth_client.get(PROFILE_URL)
        expected_action = f"/expenses/{demo_expense_id}/delete".encode()
        assert expected_action in resp.data, (
            f"profile.html must contain a form with action='{expected_action.decode()}' "
            f"for expense id={demo_expense_id}"
        )

    def test_profile_delete_button_title_attribute(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        assert b'title="Delete expense"' in resp.data or b"title='Delete expense'" in resp.data, (
            "The delete submit button must carry title=\"Delete expense\""
        )

    def test_profile_delete_button_text(self, auth_client):
        resp = auth_client.get(PROFILE_URL)
        assert b"Delete" in resp.data, (
            "The delete button must display the text 'Delete'"
        )

    def test_profile_shows_delete_form_per_expense(
        self, auth_client, all_demo_expense_ids
    ):
        """Each seeded expense must have its own delete form action URL in the profile."""
        resp = auth_client.get(PROFILE_URL)
        for eid in all_demo_expense_ids:
            action = f"/expenses/{eid}/delete".encode()
            assert action in resp.data, (
                f"profile.html must contain a delete form action for expense id={eid}"
            )

    def test_profile_delete_form_is_inside_expense_rows(self, auth_client):
        """Sanity-check that the profile page renders the expense table/list at all."""
        resp = auth_client.get(PROFILE_URL)
        # Seeded data has known amounts; at least one must appear alongside the form
        assert b"12.50" in resp.data or b"35.00" in resp.data or b"120.00" in resp.data, (
            "profile.html must render expense rows alongside the delete form"
        )

    def test_deleted_expense_no_longer_appears_on_profile(
        self, auth_client, app, demo_expense_id
    ):
        """
        After a successful delete, the profile page must not render
        a delete form for the removed expense's id.
        """
        auth_client.post(_delete_url(demo_expense_id))
        resp = auth_client.get(PROFILE_URL)
        assert resp.status_code == 200
        gone_action = f"/expenses/{demo_expense_id}/delete".encode()
        assert gone_action not in resp.data, (
            "The delete form for the removed expense must no longer appear on the profile page"
        )


# ------------------------------------------------------------------ #
# Cross-user isolation                                                #
# ------------------------------------------------------------------ #

class TestCrossUserIsolation:
    def test_deleting_own_expense_does_not_touch_other_users_expense(
        self, auth_client, app, demo_expense_id, other_user_expense_id
    ):
        auth_client.post(_delete_url(demo_expense_id))
        other_row = _fetch_expense(app, other_user_expense_id)
        assert other_row is not None, (
            "Deleting the demo user's expense must leave the other user's expense intact"
        )
        assert other_row["amount"] == pytest.approx(10.00, abs=0.001), (
            "The other user's expense amount must be unchanged after the demo user's delete"
        )

    def test_other_user_cannot_delete_demo_expense(
        self, client, app, demo_expense_id
    ):
        """
        Log in as the second user and attempt to delete the demo user's expense.
        Must return 403 and leave the row in place.
        """
        # Register and log in as the second user
        with app.app_context():
            create_user("Other User", "other2@spendly.com", "pass456")
        client.post(
            "/login",
            data={"email": "other2@spendly.com", "password": "pass456"},
            follow_redirects=False,
        )
        resp = client.post(_delete_url(demo_expense_id))
        assert resp.status_code == 403, (
            "A second authenticated user must not be able to delete another user's expense (403)"
        )
        row = _fetch_expense(app, demo_expense_id)
        assert row is not None, (
            "The demo user's expense must still exist after a rejected cross-user delete"
        )


# ------------------------------------------------------------------ #
# Route type safety — int converter                                   #
# ------------------------------------------------------------------ #

class TestRouteTypeSafety:
    @pytest.mark.parametrize("bad_id", ["abc", "1.5", "null", "--", "0x1F"])
    def test_non_integer_id_returns_404(self, auth_client, bad_id):
        """
        Flask's <int:id> converter rejects non-integer path segments at the
        routing layer, returning 404 before the view function executes.
        """
        resp = auth_client.post(f"/expenses/{bad_id}/delete")
        assert resp.status_code == 404, (
            f"Non-integer id '{bad_id}' must produce a 404 at the routing level"
        )
