# Spec: Delete Expense

## Overview
This feature allows logged-in users to delete one of their own expenses. The delete action is triggered via a POST request from a confirmation button on the profile page (or an inline form), removes the record from the database, and redirects back to the profile page with a flash message. A stub route already exists at `GET /expenses/<id>/delete` in `app.py` — this step replaces that stub with a proper POST-based delete handler and adds the `delete_expense` DB helper.

## Depends on
- Step 01: Database setup (users and expenses tables)
- Step 02: Registration
- Step 03: Login and Logout
- Step 04 & 05: Profile page with expense list
- Step 07: Add expense (so expenses exist to delete)
- Step 08: Edit expense (establishes the ownership-check pattern this step reuses)

## Routes
- `POST /expenses/<int:id>/delete` — verifies ownership, deletes the expense, redirects to profile — logged-in only

The existing `GET /expenses/<id>/delete` stub must be replaced; the new route accepts POST only to prevent accidental deletion via URL navigation or prefetch.

## Database changes
No new tables or columns. A new helper `delete_expense(expense_id)` must be added to `database/db.py`.

## Templates
- **Modify:** `templates/profile.html` — add a small delete form (method POST) for each expense row in the expense list. The form posts to `url_for('delete_expense', id=expense.id)`. Include a `title="Delete"` or similar affordance so the action is clear to the user.

## Files to change
- `app.py` — replace the stub `delete_expense` route with a POST-only implementation
- `database/db.py` — add `delete_expense(expense_id)` helper
- `templates/profile.html` — add delete form per expense row
- `app.py` imports — add `delete_expense` to the import from `database.db`

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — never f-strings in SQL
- Passwords hashed with werkzeug (not relevant here, but stated for completeness)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Route must be POST only — remove the existing GET stub entirely
- Ownership check required: fetch the expense by id, confirm `expense["user_id"] == session["user_id"]`, `abort(403)` if not
- `abort(404)` if the expense does not exist
- `abort(401)` if not logged in
- Redirect to `url_for("profile")` after successful delete (preserve any active date filter query params if possible, but a plain redirect is acceptable)
- Do not render a separate confirmation page — use the inline POST form pattern established by the edit flow

## Definition of done
- [ ] `POST /expenses/<id>/delete` deletes the expense and redirects to `/profile` with flash "Expense deleted."
- [ ] Visiting the route while not logged in returns 401
- [ ] Posting with an id that does not exist returns 404
- [ ] Posting with an id owned by a different user returns 403
- [ ] The deleted expense no longer appears in the expense list on `/profile`
- [ ] `delete_expense(expense_id)` exists in `database/db.py` and issues a parameterised DELETE query
- [ ] Each expense row on `profile.html` has a delete form that posts to the correct URL via `url_for()`
- [ ] No hardcoded URLs in any template
