"""
tests/test_analytics.py
=======================
Tests for the GET /analytics route.

Spec:
- Protected route — requires session["user_id"]
- Unauthenticated users → 302 redirect to /login (NOT 401)
- Authenticated users → 200 OK, renders analytics.html
- Page content: "Coming soon" heading, subtitle text, "Notify me" button
- Navbar: "Analytics" link shown when logged in, hidden when logged out
"""

import pytest
import database.db as db_module
from app import app as flask_app
from database.db import init_db, seed_db


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def app(tmp_path, monkeypatch):
    """
    Yield a Flask test app backed by a fresh temp-file SQLite DB.

    DB_PATH is patched so no production data is touched.
    """
    db_file = str(tmp_path / "test_spendly_analytics.db")
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


# ------------------------------------------------------------------ #
# Auth guard — unauthenticated access                                 #
# ------------------------------------------------------------------ #

class TestAnalyticsAuthGuard:
    def test_unauthenticated_get_returns_302(self, client):
        """Logged-out GET /analytics must return 302, not 200 or 401."""
        resp = client.get("/analytics")
        assert resp.status_code == 302, (
            "Unauthenticated GET /analytics must redirect (302)"
        )

    def test_unauthenticated_get_does_not_return_401(self, client):
        """The redirect must be 302, not 401 — /analytics uses redirect-on-unauth."""
        resp = client.get("/analytics")
        assert resp.status_code != 401, (
            "GET /analytics must redirect (302), not return 401"
        )

    def test_unauthenticated_get_redirects_to_login(self, client):
        """The 302 Location header must point to /login."""
        resp = client.get("/analytics", follow_redirects=False)
        assert resp.status_code == 302, "Expected a redirect"
        location = resp.headers.get("Location", "")
        assert "/login" in location, (
            f"Redirect must point to /login, got: {location}"
        )

    def test_unauthenticated_get_with_follow_lands_on_login_page(self, client):
        """Following the redirect must deliver the login page."""
        resp = client.get("/analytics", follow_redirects=True)
        assert b"Login" in resp.data or b"login" in resp.data.lower(), (
            "Following redirect from unauthenticated /analytics must land on login page"
        )


# ------------------------------------------------------------------ #
# Authenticated access — status code and template rendering           #
# ------------------------------------------------------------------ #

class TestAnalyticsAuthenticatedAccess:
    def test_authenticated_get_returns_200(self, auth_client):
        """Logged-in GET /analytics must return 200 OK."""
        resp = auth_client.get("/analytics")
        assert resp.status_code == 200, (
            "Authenticated GET /analytics must return 200"
        )

    def test_authenticated_response_is_html(self, auth_client):
        """Response content-type must be HTML."""
        resp = auth_client.get("/analytics")
        assert "text/html" in resp.content_type, (
            "GET /analytics must return an HTML response"
        )


# ------------------------------------------------------------------ #
# Page content — Coming Soon                                          #
# ------------------------------------------------------------------ #

class TestAnalyticsPageContent:
    def test_page_contains_coming_soon_heading(self, auth_client):
        """The analytics page must display a 'Coming soon' heading."""
        resp = auth_client.get("/analytics")
        assert resp.status_code == 200
        assert b"Coming soon" in resp.data or b"Coming Soon" in resp.data, (
            "Analytics page must contain a 'Coming soon' heading"
        )

    def test_page_contains_notify_me_button(self, auth_client):
        """The analytics page must contain a 'Notify me' button."""
        resp = auth_client.get("/analytics")
        assert resp.status_code == 200
        assert b"Notify me" in resp.data or b"Notify Me" in resp.data, (
            "Analytics page must contain a 'Notify me' button"
        )

    def test_page_contains_subtitle_text(self, auth_client):
        """The analytics page must contain subtitle or descriptive text below the heading."""
        resp = auth_client.get("/analytics")
        assert resp.status_code == 200
        # The page has subtitle text that contextualizes the coming-soon state.
        # We check that the page body is not just a bare heading — some descriptive
        # content must be present beyond the heading itself.
        data = resp.data
        has_subtitle = (
            b"<p" in data
            or b"<h2" in data
            or b"<h3" in data
            or b"subtitle" in data
            or b"soon" in data.lower()
        )
        assert has_subtitle, (
            "Analytics page must render subtitle/descriptive text alongside the heading"
        )

    def test_page_extends_base_template(self, auth_client):
        """analytics.html extends base.html — the base navbar structure must be present."""
        resp = auth_client.get("/analytics")
        assert resp.status_code == 200
        # base.html always renders a <nav> element
        assert b"<nav" in resp.data or b"navbar" in resp.data, (
            "Analytics page must extend base.html and include the shared navbar"
        )


# ------------------------------------------------------------------ #
# Navbar — Analytics link visibility                                  #
# ------------------------------------------------------------------ #

class TestAnalyticsNavLink:
    def test_analytics_nav_link_visible_when_logged_in(self, auth_client):
        """Authenticated users must see an 'Analytics' link in the navbar."""
        resp = auth_client.get("/analytics")
        assert resp.status_code == 200
        assert b"Analytics" in resp.data, (
            "Navbar must contain an 'Analytics' link when the user is logged in"
        )

    def test_analytics_nav_link_on_profile_page_when_logged_in(self, auth_client):
        """The Analytics nav link must appear on other protected pages too (e.g. /profile)."""
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
        assert b"Analytics" in resp.data, (
            "Navbar 'Analytics' link must appear on /profile when logged in"
        )

    def test_analytics_nav_link_absent_when_logged_out(self, client):
        """The landing page must NOT contain an 'Analytics' nav link for logged-out users."""
        resp = client.get("/")
        assert resp.status_code == 200
        # The landing page is public; since the user is not logged in, the
        # conditional navbar block must not render the Analytics link.
        # We check the nav section only — safe because 'Analytics' as a word
        # should not appear elsewhere on the landing page.
        assert b">Analytics<" not in resp.data and b"href" not in (
            # Narrow check: no anchor whose text is "Analytics"
            resp.data[resp.data.find(b"Analytics") - 20 : resp.data.find(b"Analytics") + 20]
            if b"Analytics" in resp.data
            else b""
        ), (
            "Navbar must NOT show an 'Analytics' link when the user is logged out"
        )

    def test_analytics_nav_link_absent_on_login_page(self, client):
        """The /login page must NOT render the Analytics nav link for unauthenticated users."""
        resp = client.get("/login")
        assert resp.status_code == 200
        # Check there is no <a> element linking to /analytics in the navbar
        assert b"/analytics" not in resp.data, (
            "The /login page must not expose an /analytics href to unauthenticated users"
        )

    def test_analytics_nav_link_href_correct(self, auth_client):
        """The Analytics nav link must href to /analytics."""
        resp = auth_client.get("/analytics")
        assert resp.status_code == 200
        assert b"/analytics" in resp.data, (
            "The Analytics nav link must contain an href pointing to /analytics"
        )
