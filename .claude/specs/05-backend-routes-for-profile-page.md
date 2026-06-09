# Spec: Backend Routes for Profile Page

## Overview
Step 04 delivered the profile page as a read-only display of the user's account details
and spending summary. This step adds the write-side backend: two POST routes that let a
logged-in user update their name/email and change their password. The profile page becomes
interactive — each editable section gets its own small form that submits in-place and
redisplays the profile with a flash message. This is a prerequisite for any future
account-management features and rounds out the authenticated user experience before the
expense CRUD steps begin.

## Depends on
- Step 01 — Database Setup (`users` table, `get_db()`)
- Step 02 — Registration (`create_user`, password hashing)
- Step 03 — Login and Logout (`session["user_id"]` available)
- Step 04 — Profile Page (`GET /profile`, `profile.html`, `get_user_by_id()`, `get_expense_summary()`)

## Routes
- `POST /profile/edit` — validate and update the user's name and email — logged-in only
- `POST /profile/password` — validate and update the user's password — logged-in only

Both routes redirect back to `GET /profile` on success or failure (POST-Redirect-GET pattern),
using `flash()` to communicate the outcome.

## Database changes
No new tables or columns. Two new write helper functions are required in `database/db.py`:

- `update_user(user_id, name, email)` — updates `name` and `email` for the given user id.
  Must raise `sqlite3.IntegrityError` naturally if the new email is already taken by another
  account (the UNIQUE constraint on `users.email` handles this automatically).
- `update_password(user_id, new_password_hash)` — updates `password_hash` for the given user id.

Both must use parameterised placeholders (`?`) — no f-strings in SQL.

## Templates
- **Modify:** `templates/profile.html` — add two inline edit forms:
  1. **Edit Info form** — fields for `name` and `email`, POSTs to `url_for('edit_profile')`
  2. **Change Password form** — fields for `current_password`, `new_password`, `confirm_password`,
     POSTs to `url_for('change_password')`
  - Flash messages must be displayed at the top of the page (already in `base.html`; confirm
    the block is wired up in `profile.html`)
  - All form inputs must have `name` attributes matching what the route expects
  - Use `url_for()` for every `action` attribute — no hardcoded paths

## Files to change
- `app.py` — add `edit_profile()` and `change_password()` route handlers; import
  `update_user` and `update_password` from `database.db`
- `database/db.py` — add `update_user()` and `update_password()` helpers
- `templates/profile.html` — add the two edit forms
- `static/css/profile.css` — add styles for the inline edit forms (input fields, submit
  buttons, form section layout)

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — no f-strings in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash`; verified with
  `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values; use variables already defined in `style.css`
- All templates extend `base.html`
- Both POST routes must `abort(401)` if `session["user_id"]` is not set
- Use the POST-Redirect-GET pattern: both routes always end with
  `redirect(url_for('profile'))` — never re-render the template directly from a POST
- `update_user` and `update_password` must live in `database/db.py` — never inline SQL in routes
- Email uniqueness errors from `update_user` must be caught as `sqlite3.IntegrityError`
  and shown as a flash message — do not let the 500 propagate
- Current password must be verified with `check_password_hash` before calling `update_password`
- New password must be at least 8 characters; `new_password` must match `confirm_password`
- A successful edit must update `session["user_name"]` if the name changes, so the navbar
  stays in sync without requiring a re-login

## Definition of done
- [ ] `POST /profile/edit` with valid name and email updates the database and flashes a success message
- [ ] `POST /profile/edit` with an email already in use flashes an error and does not update
- [ ] `POST /profile/edit` with a blank name flashes a validation error and does not update
- [ ] After a successful name change, `session["user_name"]` reflects the new name immediately
- [ ] `POST /profile/password` with correct current password and matching new passwords updates the hash
- [ ] `POST /profile/password` with a wrong current password flashes an error and does not update
- [ ] `POST /profile/password` where new passwords don't match flashes an error and does not update
- [ ] `POST /profile/password` with a new password under 8 characters flashes a validation error
- [ ] Both routes return 401 when the user is not logged in
- [ ] Both forms are visible and functional on the profile page at a desktop viewport
- [ ] No hardcoded URLs in `profile.html` — all form `action` attributes use `url_for()`
