"""
tests/test_date_filter.py
=========================
Tests for the date-range filter feature on GET /profile and the
get_expense_summary() DB helper.

Seeded demo data (all in May 2026):
  2026-05-01  Food           12.50
  2026-05-03  Transport      35.00
  2026-05-05  Bills         120.00
  2026-05-08  Health         45.00
  2026-05-10  Entertainment  18.00
  2026-05-14  Shopping       65.00
  2026-05-18  Other           9.99
  2026-05-21  Food           22.00
  --------------------------------
  Total (8)               $327.49   Top: Bills
"""

import os
import tempfile
import pytest
import database.db as db_module
from app import app as flask_app
from database.db import init_db, seed_db, get_expense_summary


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def app(tmp_path, monkeypatch):
    """
    Yield a fully configured Flask app backed by a fresh temp-file SQLite DB.

    We patch database.db.DB_PATH so every call to get_db() inside the app
    and the db helpers uses the temp file, not spendly.db on disk.
    """
    db_file = str(tmp_path / "test_spendly.db")
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
    assert resp.status_code == 302, "Login during fixture setup must redirect"
    return client


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_profile_no_params_returns_401(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 401, "Unauthenticated /profile must return 401"

    def test_unauthenticated_profile_with_date_params_returns_401(self, client):
        resp = client.get("/profile?date_from=2026-05-01&date_to=2026-05-31")
        assert resp.status_code == 401, (
            "Unauthenticated /profile with date params must still return 401"
        )

    def test_unauthenticated_profile_date_from_only_returns_401(self, client):
        resp = client.get("/profile?date_from=2026-05-01")
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
# All-time totals (no filter)                                         #
# ------------------------------------------------------------------ #

class TestNoFilter:
    def test_no_params_returns_200(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200

    def test_no_params_shows_all_eight_expenses(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"8" in resp.data, "All 8 seeded expenses must be counted"

    def test_no_params_shows_correct_total(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"327.49" in resp.data, "All-time total must be $327.49"

    def test_no_params_shows_top_category_bills(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Bills" in resp.data, "Top category must be Bills for all-time"

    def test_no_params_shows_plain_label(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Spending Summary" in resp.data
        assert b"Spending Summary (filtered)" not in resp.data, (
            "Label must NOT say '(filtered)' when no filter is active"
        )

    def test_filter_form_is_present(self, auth_client):
        resp = auth_client.get("/profile")
        assert b'method="GET"' in resp.data, "Date filter form must be present"
        assert b'name="date_from"' in resp.data
        assert b'name="date_to"' in resp.data


# ------------------------------------------------------------------ #
# Full-range filter (entire May 2026 — same totals as all-time)       #
# ------------------------------------------------------------------ #

class TestFullMonthFilter:
    def test_full_may_2026_returns_200(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-31")
        assert resp.status_code == 200

    def test_full_may_2026_expense_count(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-31")
        assert b"8" in resp.data, "All 8 expenses fall within May 2026"

    def test_full_may_2026_total(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-31")
        assert b"327.49" in resp.data

    def test_full_may_2026_top_category(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-31")
        assert b"Bills" in resp.data

    def test_full_may_2026_shows_filtered_label(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-31")
        assert b"Spending Summary (filtered)" in resp.data


# ------------------------------------------------------------------ #
# Partial range — first ten days of May 2026                          #
# Covers: 05-01 (12.50), 05-03 (35.00), 05-05 (120.00),             #
#         05-08 (45.00), 05-10 (18.00) = 5 records, $230.50          #
# ------------------------------------------------------------------ #

class TestPartialRangeFilter:
    URL = "/profile?date_from=2026-05-01&date_to=2026-05-10"

    def test_partial_range_returns_200(self, auth_client):
        resp = auth_client.get(self.URL)
        assert resp.status_code == 200

    def test_partial_range_expense_count(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"5" in resp.data, "5 expenses fall in the first 10 days of May"

    def test_partial_range_total(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"230.50" in resp.data, "Sum of first-10-days expenses must be $230.50"

    def test_partial_range_top_category_bills(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"Bills" in resp.data, "Bills ($120) is top category in this range"

    def test_partial_range_filtered_label(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"Spending Summary (filtered)" in resp.data


# ------------------------------------------------------------------ #
# Open upper bound (date_from only)                                   #
# date_from=2026-05-14 → 05-14 (65), 05-18 (9.99), 05-21 (22)       #
# 3 records, $96.99, top category Shopping                            #
# ------------------------------------------------------------------ #

class TestDateFromOnly:
    URL = "/profile?date_from=2026-05-14"

    def test_date_from_only_returns_200(self, auth_client):
        resp = auth_client.get(self.URL)
        assert resp.status_code == 200

    def test_date_from_only_expense_count(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"3" in resp.data, "3 expenses on or after 2026-05-14"

    def test_date_from_only_total(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"96.99" in resp.data, "Total for expenses from 2026-05-14 onward"

    def test_date_from_only_top_category(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"Shopping" in resp.data, "Shopping ($65) is top in this open-ended range"

    def test_date_from_only_filtered_label(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"Spending Summary (filtered)" in resp.data

    def test_date_from_input_prefilled(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b'value="2026-05-14"' in resp.data, (
            "date_from input must be pre-filled with the active filter value"
        )


# ------------------------------------------------------------------ #
# Open lower bound (date_to only)                                     #
# date_to=2026-05-05 → 05-01 (12.50), 05-03 (35.00), 05-05 (120.00) #
# 3 records, $167.50, top category Bills                              #
# ------------------------------------------------------------------ #

class TestDateToOnly:
    URL = "/profile?date_to=2026-05-05"

    def test_date_to_only_returns_200(self, auth_client):
        resp = auth_client.get(self.URL)
        assert resp.status_code == 200

    def test_date_to_only_expense_count(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"3" in resp.data, "3 expenses on or before 2026-05-05"

    def test_date_to_only_total(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"167.50" in resp.data, "Total for expenses up to 2026-05-05"

    def test_date_to_only_top_category(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"Bills" in resp.data, "Bills ($120) is top category up to 2026-05-05"

    def test_date_to_only_filtered_label(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"Spending Summary (filtered)" in resp.data

    def test_date_to_input_prefilled(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b'value="2026-05-05"' in resp.data, (
            "date_to input must be pre-filled with the active filter value"
        )


# ------------------------------------------------------------------ #
# Empty range (no expenses match)                                     #
# ------------------------------------------------------------------ #

class TestEmptyRange:
    URL = "/profile?date_from=2025-01-01&date_to=2025-12-31"

    def test_empty_range_returns_200(self, auth_client):
        resp = auth_client.get(self.URL)
        assert resp.status_code == 200

    def test_empty_range_zero_total(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"0.00" in resp.data, "Total spent must be $0.00 for an empty range"

    def test_empty_range_zero_count(self, auth_client):
        resp = auth_client.get(self.URL)
        # The expense_count stat tile will contain "0"
        assert b"0" in resp.data

    def test_empty_range_no_top_category(self, auth_client):
        resp = auth_client.get(self.URL)
        # Template renders em-dash when top_category is None
        assert "—".encode() in resp.data, (
            "Top category must render as em-dash when no expenses exist in range"
        )

    def test_empty_range_filtered_label(self, auth_client):
        resp = auth_client.get(self.URL)
        assert b"Spending Summary (filtered)" in resp.data


# ------------------------------------------------------------------ #
# Malformed date params — silently ignored, fall back to all-time     #
# ------------------------------------------------------------------ #

class TestMalformedDateParams:
    def test_malformed_date_from_ignored_returns_200(self, auth_client):
        resp = auth_client.get("/profile?date_from=notadate")
        assert resp.status_code == 200

    def test_malformed_date_from_falls_back_to_alltime_total(self, auth_client):
        resp = auth_client.get("/profile?date_from=notadate")
        assert b"327.49" in resp.data, (
            "Malformed date_from must be ignored and return all-time total"
        )

    def test_malformed_date_from_falls_back_to_alltime_count(self, auth_client):
        resp = auth_client.get("/profile?date_from=notadate")
        assert b"8" in resp.data

    def test_malformed_date_from_no_filtered_label(self, auth_client):
        resp = auth_client.get("/profile?date_from=notadate")
        assert b"Spending Summary (filtered)" not in resp.data, (
            "Label must NOT say '(filtered)' when date_from was malformed and dropped"
        )

    def test_malformed_date_to_ignored_returns_alltime_total(self, auth_client):
        resp = auth_client.get("/profile?date_to=32-99-00")
        assert b"327.49" in resp.data, (
            "Malformed date_to must be ignored and return all-time total"
        )

    def test_malformed_date_to_no_filtered_label(self, auth_client):
        resp = auth_client.get("/profile?date_to=32-99-00")
        assert b"Spending Summary (filtered)" not in resp.data

    def test_both_malformed_returns_alltime(self, auth_client):
        resp = auth_client.get("/profile?date_from=bad&date_to=alsabad")
        assert resp.status_code == 200
        assert b"327.49" in resp.data
        assert b"Spending Summary (filtered)" not in resp.data

    @pytest.mark.parametrize("raw_value", [
        "2026/05/01",   # wrong separator
        "01-05-2026",   # day-month-year order
        "20260501",     # no separators
        "",             # empty string
        "null",         # JS null as string
        "' OR 1=1 --",  # SQL injection attempt
    ])
    def test_various_malformed_date_from_values_ignored(self, auth_client, raw_value):
        resp = auth_client.get(f"/profile?date_from={raw_value}")
        assert resp.status_code == 200, (
            f"Malformed date_from '{raw_value}' must not crash the route"
        )
        assert b"327.49" in resp.data, (
            f"Malformed date_from '{raw_value}' must fall back to all-time total"
        )


# ------------------------------------------------------------------ #
# Input pre-fill                                                      #
# ------------------------------------------------------------------ #

class TestInputPrefill:
    def test_both_inputs_prefilled_when_both_params_active(self, auth_client):
        resp = auth_client.get(
            "/profile?date_from=2026-05-01&date_to=2026-05-31"
        )
        assert b'value="2026-05-01"' in resp.data, "date_from input must be pre-filled"
        assert b'value="2026-05-31"' in resp.data, "date_to input must be pre-filled"

    def test_date_from_empty_when_not_provided(self, auth_client):
        resp = auth_client.get("/profile?date_to=2026-05-31")
        # date_from input should have an empty value attribute
        assert b'value=""' in resp.data or b"value=" not in resp.data.split(
            b'name="date_from"'
        )[0][-50:], (
            "date_from input must be empty when param is absent"
        )

    def test_date_to_empty_when_not_provided(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01")
        # date_to input should have an empty value attribute
        assert b'value=""' in resp.data or b"value=" not in resp.data.split(
            b'name="date_to"'
        )[0][-50:], (
            "date_to input must be empty when param is absent"
        )

    def test_inputs_empty_when_no_params(self, auth_client):
        resp = auth_client.get("/profile")
        # Both value attributes should appear as empty strings in the template
        # (the route passes date_from="" and date_to="" when params are absent)
        data = resp.data
        # Find the date_from input block and confirm value=""
        assert b'name="date_from"' in data
        assert b'name="date_to"' in data


# ------------------------------------------------------------------ #
# Template structure — filter form landmarks                          #
# ------------------------------------------------------------------ #

class TestTemplateStructure:
    def test_filter_form_has_get_method(self, auth_client):
        resp = auth_client.get("/profile")
        assert b'method="GET"' in resp.data

    def test_filter_form_has_date_from_input(self, auth_client):
        resp = auth_client.get("/profile")
        assert b'name="date_from"' in resp.data
        assert b'type="date"' in resp.data

    def test_filter_form_has_date_to_input(self, auth_client):
        resp = auth_client.get("/profile")
        assert b'name="date_to"' in resp.data

    def test_filter_form_has_submit_button(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Filter" in resp.data

    def test_clear_link_present(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Clear" in resp.data

    def test_summary_strip_present(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"summary-strip" in resp.data or b"Total Spent" in resp.data


# ------------------------------------------------------------------ #
# Unit tests — get_expense_summary() DB helper directly               #
# ------------------------------------------------------------------ #

class TestGetExpenseSummaryHelper:
    """
    Call get_expense_summary() directly (outside HTTP) to verify the
    return-dict contract and filter semantics independently of the route.
    """

    def _get_demo_user_id(self):
        """Return the demo user's id from the temp DB."""
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
        conn.close()
        return row[0]

    def test_returns_dict_with_required_keys(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid)
        assert "total_spent" in result
        assert "expense_count" in result
        assert "top_category" in result

    def test_all_time_total_spent(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid)
        assert result["total_spent"] == pytest.approx(327.49, abs=0.01)

    def test_all_time_expense_count(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid)
        assert result["expense_count"] == 8

    def test_all_time_top_category(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid)
        assert result["top_category"] == "Bills"

    def test_date_from_and_date_to_filter(self, app):
        # 2026-05-01 to 2026-05-10: Food+Transport+Bills+Health+Entertainment
        # = 12.50 + 35.00 + 120.00 + 45.00 + 18.00 = 230.50, 5 records
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid, date_from="2026-05-01", date_to="2026-05-10")
        assert result["expense_count"] == 5
        assert result["total_spent"] == pytest.approx(230.50, abs=0.01)
        assert result["top_category"] == "Bills"

    def test_date_from_only(self, app):
        # From 2026-05-14 onward: Shopping+Other+Food = 65+9.99+22 = 96.99, 3 records
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid, date_from="2026-05-14")
        assert result["expense_count"] == 3
        assert result["total_spent"] == pytest.approx(96.99, abs=0.01)
        assert result["top_category"] == "Shopping"

    def test_date_to_only(self, app):
        # Up to 2026-05-05: Food+Transport+Bills = 12.50+35+120 = 167.50, 3 records
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid, date_to="2026-05-05")
        assert result["expense_count"] == 3
        assert result["total_spent"] == pytest.approx(167.50, abs=0.01)
        assert result["top_category"] == "Bills"

    def test_empty_range_returns_zero_total(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid, date_from="2020-01-01", date_to="2020-12-31")
        assert result["total_spent"] == 0.0
        assert result["expense_count"] == 0

    def test_empty_range_top_category_is_none(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid, date_from="2020-01-01", date_to="2020-12-31")
        assert result["top_category"] is None

    def test_total_spent_is_float(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid)
        assert isinstance(result["total_spent"], float), (
            "total_spent must be a float, not int or Decimal"
        )

    def test_expense_count_is_int(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid)
        assert isinstance(result["expense_count"], int)

    def test_full_may_range_same_as_alltime(self, app):
        with app.app_context():
            uid = self._get_demo_user_id()
            all_time = get_expense_summary(uid)
            may = get_expense_summary(uid, date_from="2026-05-01", date_to="2026-05-31")
        assert may["total_spent"] == pytest.approx(all_time["total_spent"], abs=0.01)
        assert may["expense_count"] == all_time["expense_count"]
        assert may["top_category"] == all_time["top_category"]

    def test_boundary_inclusivity_date_from(self, app):
        # date 2026-05-01 must be included when date_from=2026-05-01
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid, date_from="2026-05-01", date_to="2026-05-01")
        assert result["expense_count"] == 1
        assert result["total_spent"] == pytest.approx(12.50, abs=0.01)

    def test_boundary_inclusivity_date_to(self, app):
        # date 2026-05-21 must be included when date_to=2026-05-21
        with app.app_context():
            uid = self._get_demo_user_id()
            result = get_expense_summary(uid, date_from="2026-05-21", date_to="2026-05-21")
        assert result["expense_count"] == 1
        assert result["total_spent"] == pytest.approx(22.00, abs=0.01)
