# Spec: Profile Page Design

## Overview
This step implements the `/profile` route, replacing the current stub with a fully rendered
page that displays the logged-in user's account details and a summary of their expense
activity. The page is private (logged-in only) and serves as the user's personal dashboard
for reviewing who they are and a high-level view of their spending totals.

## Depends on
- Step 01 — Database Setup (users and expenses tables, `get_db()`)
- Step 02 — Registration (`create_user()`, users table populated)
- Step 03 — Login and Logout (session with `session["user_id"]`)

## Routes
- `GET /profile` — renders the profile page for the current user — logged-in only

## Database changes
No new tables or columns needed. Two new read-only helper functions are required in
`database/db.py` to fetch data the profile page needs:

- `get_user_by_id(user_id)` — returns the users row for the given id, or `None`
- `get_expense_summary(user_id)` — returns a dict with:
  - `total_spent` — sum of all expense amounts (REAL, 0.0 if none)
  - `expense_count` — total number of expense rows (int)
  - `top_category` — category with the highest total spend, or `None` if no expenses

Both queries must use parameterised placeholders (`?`).

## Templates
- **Create:** `templates/profile.html` — profile page extending `base.html`
- **Modify:** none

### `profile.html` layout
The page should contain three visual sections:

1. **Account card** — user's name, email, and "Member since" date (formatted as `Month DD, YYYY`)
2. **Spending summary strip** — three stat tiles:
   - Total Spent (currency-formatted)
   - Number of Expenses
   - Top Category (or "—" when no expenses)
3. **Action row** — a single "Back to Home" link using `url_for('index')`

## Files to change
- `app.py` — replace the `/profile` stub with a real route handler
- `database/db.py` — add `get_user_by_id()` and `get_expense_summary()`

## Files to create
- `templates/profile.html`
- `static/css/profile.css` — page-specific styles (imported via a `{% block head %}` block in `profile.html`)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — no f-strings in SQL
- Passwords are never read or displayed on this page
- Use CSS variables — never hardcode hex values; use variables already defined in `style.css`
- All templates must extend `base.html`
- Unauthenticated requests to `GET /profile` must `abort(401)` — do not redirect silently
- Route function has one responsibility: fetch data, pass to template — no business logic inline
- `get_user_by_id` and `get_expense_summary` must live in `database/db.py`, never inline in the route
- Format currency in the template with Jinja2's `| round(2)` filter and a `$` prefix — no JS formatting
- `top_category` query must use `GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1`

## Definition of done
- [ ] `GET /profile` renders `profile.html` (HTTP 200) when the user is logged in
- [ ] The account card displays the correct name, email, and member-since date for the logged-in user
- [ ] Total Spent shows `$0.00` when the user has no expenses
- [ ] Total Spent shows the correct sum when the user has expenses
- [ ] Top Category shows `—` when the user has no expenses
- [ ] Top Category shows the correct category when expenses exist
- [ ] Visiting `/profile` while logged out returns HTTP 401
- [ ] No hardcoded URLs in `profile.html` — all links use `url_for()`
- [ ] Page passes manual visual check: three sections are visible and readable on a desktop viewport
