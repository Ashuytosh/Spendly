# Spec: Date Filter for Profile Page

## Overview
The Spending Summary on the profile page currently shows all-time totals regardless
of when expenses were incurred. This step adds a date-range filter so users can scope
the summary stats (Total Spent, Number of Expenses, Top Category) to a specific period —
e.g. "this month", "last 30 days", or a custom from/to window. The filter is submitted
as a GET form on the profile page, the route reads the query-string params, passes them
to the DB helper, and re-renders the page with filtered summary data. No new routes are
required — only the existing `GET /profile` route is extended.

## Depends on
- Step 01 — Database Setup (`expenses` table, `get_db()`)
- Step 02 — Registration (users table populated)
- Step 03 — Login and Logout (`session["user_id"]` required)
- Step 04 — Profile Page (`GET /profile`, `profile.html`, `get_expense_summary()`)
- Step 05 — Backend Routes for Profile Page (profile edit forms in place)

## Routes
No new routes. `GET /profile` is extended to read optional query-string parameters:
- `date_from` — ISO date string `YYYY-MM-DD`, inclusive lower bound (optional)
- `date_to`   — ISO date string `YYYY-MM-DD`, inclusive upper bound (optional)

When neither param is present the summary behaves identically to today (all-time totals).

## Database changes
No new tables or columns.

One existing helper is updated:

- `get_expense_summary(user_id, date_from=None, date_to=None)` — adds two optional
  keyword arguments. When provided, a `WHERE date BETWEEN ? AND ?` clause is appended
  to both sub-queries (total/count and top-category). Must use parameterised `?`
  placeholders — never f-string interpolation.

## Templates
- **Modify:** `templates/profile.html`
  - Add a date-filter form above the Spending Summary strip. The form uses `method="GET"`
    and `action="{{ url_for('profile') }}"`.
  - Two `<input type="date">` fields: `name="date_from"` and `name="date_to"`.
  - Their `value` attributes are pre-filled with the current filter values so the form
    remembers what the user selected.
  - A "Filter" submit button and a "Clear" link that navigates to `url_for('profile')`
    with no query params, resetting to all-time view.
  - The section label above the strip should reflect the active filter:
    - No filter active → "Spending Summary"
    - Filter active → "Spending Summary (filtered)"

## Files to change
- `app.py` — read `date_from` and `date_to` from `request.args` in the `profile()` route;
  validate that both are valid `YYYY-MM-DD` dates when present (silently ignore malformed
  values); pass them to `get_expense_summary()`; pass the raw strings back to the template
  as `date_from` and `date_to` context variables.
- `database/db.py` — update `get_expense_summary()` signature to accept `date_from=None`
  and `date_to=None`; conditionally extend both SQL queries with a `BETWEEN` clause.
- `templates/profile.html` — add the filter form as described above.
- `static/css/profile.css` — add styles for the filter form row (date inputs, Filter button,
  Clear link, compact layout).

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — no f-strings in SQL; build the WHERE clause by appending
  `?` placeholders and extending the params tuple
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `GET /profile` must still `abort(401)` if `session["user_id"]` is not set
- Malformed date strings in query params must be silently ignored (fall back to `None`),
  not raise a 500 — use `datetime.strptime` inside a `try/except ValueError`
- The filter form must use `method="GET"` so the filtered URL is bookmarkable
- When `date_from` is provided but `date_to` is omitted (or vice versa), the single
  bound is still applied (open-ended range): `date >= date_from` or `date <= date_to`
- The route function must not contain inline SQL — all query logic stays in `database/db.py`
- `get_expense_summary()` signature change must remain backwards-compatible (defaults to
  `None`) so existing call sites without filter args continue to work

## Definition of done
- [ ] `GET /profile` with no query params shows the same all-time summary as before this step
- [ ] `GET /profile?date_from=2026-05-01&date_to=2026-05-31` returns summary scoped to May 2026
- [ ] Total Spent and Expenses count are both 0 (or $0.00 / 0) when no expenses fall in the range
- [ ] Top Category shows `—` when no expenses fall in the selected range
- [ ] The date-filter form on the profile page pre-fills the inputs with the active filter values
- [ ] Clicking "Clear" navigates to `/profile` with no query params and restores all-time totals
- [ ] The section label reads "Spending Summary (filtered)" when a filter is active
- [ ] A malformed `date_from` or `date_to` value (e.g. `?date_from=notadate`) is silently ignored
- [ ] Only `date_from` provided: expenses from that date to the present are counted
- [ ] Only `date_to` provided: all expenses up to and including that date are counted
- [ ] No hardcoded URLs in `profile.html` — all links and form actions use `url_for()`
- [ ] Unauthenticated `GET /profile?date_from=...` still returns HTTP 401
