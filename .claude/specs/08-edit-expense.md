# Spec: Edit Expense

## Overview
This feature lets a logged-in user edit an existing expense they own. It replaces the current `GET /expenses/<id>/edit` stub with a full `GET`/`POST` handler that loads the existing record, pre-fills a form, validates changes, and persists them. To make the route reachable, the profile page also gains an expense list (respecting the existing date filter) where each row has an Edit button. Ownership is enforced: a user cannot edit another user's expense.

## Depends on
- Step 01 — Database setup (`expenses` table in `init_db`)
- Step 02 — Registration (user must exist)
- Step 03 — Login/Logout (session-based auth)
- Step 04/05/06 — Profile page with date filter (edit redirects back here; expense list is added here)
- Step 07 — Add Expense (same category list and validation rules)

## Routes
- `GET /expenses/<int:id>/edit` — Render pre-filled edit form for the given expense — logged-in only
- `POST /expenses/<int:id>/edit` — Validate and persist the updated expense, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. Two new DB helpers are required:

- `get_expense_by_id(expense_id)` — fetches a single expense row by `id`; returns `None` if not found
- `get_expenses_for_user(user_id, date_from=None, date_to=None)` — returns all expenses for a user ordered by `date DESC`, with optional date range filtering (mirrors the filter logic in `get_expense_summary`)
- `update_expense(expense_id, amount, category, date, description)` — updates `amount`, `category`, `date`, `description` for the given row

## Templates
- **Create:** `templates/edit_expense.html` — pre-filled form with fields: amount, category (dropdown), date, description (optional); mirrors `add_expense.html` structure
- **Modify:** `templates/profile.html` — add an Expense List section below the Spending Summary that renders the expense rows (from a new `expenses` template variable) with an Edit button per row linking to `url_for('edit_expense', id=expense.id)`

## Files to change
- `app.py` — replace the stub `edit_expense` route with a full `GET`/`POST` implementation; import the new DB helpers; pass `expenses` list to the `profile` route's `render_template` call
- `database/db.py` — add `get_expense_by_id`, `get_expenses_for_user`, and `update_expense` helpers

## Files to create
- `templates/edit_expense.html` — edit form template
- `static/css/edit_expense.css` — page-specific styles (linked only from `edit_expense.html`)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — never f-strings in SQL
- Passwords hashed with werkzeug (not applicable here, but keep the rule)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Unauthenticated access to either route must call `abort(401)`
- Ownership check: after fetching the expense, confirm `expense["user_id"] == session["user_id"]`; if not, call `abort(403)`
- If the expense does not exist, call `abort(404)`
- Reuse `VALID_CATEGORIES` from `app.py` for category validation (same list as add-expense)
- `amount` must be a positive finite float — reject zero or negative values
- `date` must be a valid `YYYY-MM-DD` string — reuse the existing `_parse_date` helper
- `description` is optional; store `None` if blank
- On validation failure, re-render the edit form with a `flash` message (do not redirect)
- On success, flash a confirmation message and redirect to `url_for("profile")`
- `get_expenses_for_user` must apply date filter params the same way `get_expense_summary` does — keep them in sync
- The expense list in `profile.html` must respect the existing `date_from` / `date_to` filter (pass them through to `get_expenses_for_user`)
- The Edit button link must preserve active date filter params via `url_for` query args where relevant (not strictly required — redirect after edit always goes to unfiltered profile)

## Definition of done
- [ ] `GET /expenses/<id>/edit` returns 200 for the expense owner with a pre-filled form
- [ ] `GET /expenses/<id>/edit` returns 401 for an unauthenticated user
- [ ] `GET /expenses/<id>/edit` returns 403 when a logged-in user tries to edit another user's expense
- [ ] `GET /expenses/<id>/edit` returns 404 for a non-existent expense id
- [ ] Submitting the form with valid data updates the expense row and redirects to `/profile`
- [ ] The updated values are visible in the profile expense list after redirect
- [ ] Submitting with a missing or non-positive amount re-renders the form with an error flash
- [ ] Submitting with an invalid category re-renders the form with an error flash
- [ ] Submitting with an invalid or missing date re-renders the form with an error flash
- [ ] All form field values reflect the submitted (invalid) input after a validation failure
- [ ] The profile page shows the expense list with an Edit button per row
- [ ] The expense list on the profile page respects the active date filter
