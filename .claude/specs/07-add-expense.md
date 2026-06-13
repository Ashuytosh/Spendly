# Spec: Add Expense

## Overview
This feature implements the "Add Expense" page, allowing a logged-in user to submit a new expense entry via a form. It replaces the current stub route with a real `GET`/`POST` handler that validates input, persists the expense to the database via a new `create_expense` helper in `database/db.py`, and redirects back to the profile page on success. This is the first step that lets users populate their own expense data beyond the seeded demo records.

## Depends on
- Step 01 — Database setup (`expenses` table already exists in `init_db`)
- Step 02 — Registration (user must exist)
- Step 03 — Login/Logout (session-based auth required)
- Step 04/05 — Profile page (redirect destination after save)

## Routes
- `GET /expenses/add` — Render the add-expense form — logged-in only
- `POST /expenses/add` — Validate and persist a new expense, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. The `expenses` table already has all required columns:
`id`, `user_id`, `amount`, `category`, `date`, `description`, `created_at`.

A new DB helper is required:
- `create_expense(user_id, amount, category, date, description)` — inserts one row into `expenses`.

## Templates
- **Create:** `templates/add_expense.html` — form with fields: amount, category (dropdown), date, description (optional)
- **Modify:** none

## Files to change
- `app.py` — replace the stub `add_expense` route with a full `GET`/`POST` implementation
- `database/db.py` — add `create_expense` helper
- `app.py` imports — add `create_expense` to the import from `database.db`

## Files to create
- `templates/add_expense.html` — the add-expense form template
- `static/css/add_expense.css` — page-specific styles (linked only from `add_expense.html`)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — never f-strings in SQL
- Passwords hashed with werkzeug (not applicable here, but keep the rule)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Unauthenticated access to either route must call `abort(401)`
- `amount` must be a positive float — reject zero or negative values
- `category` must be one of the fixed allowed values: Food, Transport, Bills, Health, Entertainment, Shopping, Other
- `date` must be a valid `YYYY-MM-DD` string — use the existing `_parse_date` helper
- `description` is optional; store `None` if blank
- On validation failure, re-render the form with a `flash` message (do not redirect)
- On success, flash a confirmation message and redirect to `url_for("profile")`
- The `create_expense` helper lives in `database/db.py`, not inline in the route

## Definition of done
- [ ] `GET /expenses/add` returns 200 for a logged-in user and renders the add-expense form
- [ ] `GET /expenses/add` returns 401 for an unauthenticated user
- [ ] Submitting the form with valid data creates a new row in the `expenses` table and redirects to `/profile`
- [ ] The new expense appears in the profile summary (total and count update)
- [ ] Submitting with a missing or non-positive amount re-renders the form with an error flash
- [ ] Submitting with an invalid category re-renders the form with an error flash
- [ ] Submitting with an invalid or missing date re-renders the form with an error flash
- [ ] Description field is optional — form submits successfully when left blank
- [ ] All form field values are repopulated after a validation failure
