# Implementation Plan: User Registration (Step 02)

## Goal Description
Implement the user registration feature for Spendly based on the spec in `.claude/specs/02-registration.md`.

This feature allows new users to register an account using their full name, email address, and a secure password. Following Step 01's database foundation, this step introduces user creation into the SQLite `users` table via `POST /register`, performs input validation, hashes passwords securely using `werkzeug.security`, preserves form inputs on error, and redirects to `/login` upon success.

---

## User Review Required

> [!IMPORTANT]
> **Post-Registration Flow:** On successful registration, users are redirected to `GET /login`. In accordance with the roadmap, sessions and login authentication are part of Step 03 (Login and Logout), so users are not automatically logged in immediately after registering.

> [!NOTE]
> **Validation & Security Standards:**
> - Full name and email have leading/trailing whitespace stripped; email is normalized to lowercase.
> - Password minimum length of 8 characters is strictly enforced on both client (`minlength="8"`) and server.
> - Passwords are never stored in plain text and are hashed using Werkzeug.
> - On validation or duplicate email failure, entered `name` and `email` are preserved in the form so the user does not have to retype them; password is cleared for security.

---

## Open Questions

None. The requirements in `.claude/specs/02-registration.md` are comprehensive and align with the existing schema and UI templates.

---

## Proposed Changes

### Component 1 — Application Routing & Logic
- Modify `app.py` to handle `GET` and `POST` for `/register`.
- Validate input fields, check for existing email, hash passwords using `generate_password_hash`, insert user into `users` table, and redirect to `/login`.

### Component 2 — User Interface & Template
- Modify `templates/register.html` to preserve user input (`value="{{ name or '' }}"`, `value="{{ email or '' }}"`) and set `minlength="8"` on password input.

---

## Verification Plan

### Automated Tests
Run tests verifying:
1. `GET /register` returns 200 with registration form.
2. `POST /register` with missing fields fails with error message and preserves inputs.
3. `POST /register` with password < 8 characters fails.
4. `POST /register` with invalid email format fails.
5. `POST /register` with existing email (`demo@spendly.com`) fails with duplicate message.
6. `POST /register` with valid new user creates record in DB with hashed password and redirects to `/login`.

### Manual Verification
1. Open browser to `/register`.
2. Test submitting empty or invalid inputs and verify error messages.
3. Test registering duplicate email `demo@spendly.com`.
4. Register a new user and verify redirect to `/login` and DB row in SQLite.
