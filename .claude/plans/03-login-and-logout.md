# Implementation Plan: Login and Logout (Step 03)

## Goal Description
Implement session-based authentication for Spendly as specified in `.claude/specs/03-login-and-logout.md`.

This feature allows registered users to sign in using their email and password, validates credentials against the SQLite database using `check_password_hash`, maintains session state across requests using Flask's signed cookie sessions, conditionally updates the navigation bar in `base.html` based on authentication status, and enables users to log out safely.

---

## User Review Required

> [!IMPORTANT]
> **Session Secret Key (`app.secret_key`):**
> Flask requires `app.secret_key` to sign session cookies. Configured to use `os.environ.get("SECRET_KEY", "spendly-dev-secret-key-change-in-production")`.

> [!NOTE]
> **Enumeration Prevention & Security:**
> - When authentication fails (whether the email is not registered or the password is incorrect), the app returns the generic message: `"Invalid email or password."`.
> - On authentication failure, the entered email is preserved in the form, but the password field is always cleared for security.
> - If an already authenticated user visits `/login` or `/register`, they will be automatically redirected to `/profile`.

---

## Open Questions

None. All requirements in `.claude/specs/03-login-and-logout.md` are comprehensive and align with the existing architecture.

---

## Proposed Changes

### Component 1 — Backend & Session Management
- Modify `app.py`:
  - Import `session` and `check_password_hash`.
  - Set `app.secret_key`.
  - Implement `POST` on `/login` with database lookup, `check_password_hash`, and session assignment.
  - Implement `/logout` to clear session and redirect to `/login`.
  - Redirect already authenticated users from `/login` and `/register` to `/profile`.

### Component 2 — User Interface & Templates
- Modify `templates/login.html` to retain email input (`value="{{ email or '' }}"`) upon error.
- Modify `templates/base.html` to conditionally display `Profile` and `Logout` when `session.get('user_id')` is set, or `Sign in` and `Get started` when not set.

---

## Verification Plan

### Automated Tests
Run tests verifying:
1. `GET /login` renders form.
2. `POST /login` with missing fields fails with error message and preserves email.
3. `POST /login` with non-existent email returns `"Invalid email or password."`.
4. `POST /login` with invalid password returns `"Invalid email or password."`.
5. `POST /login` with valid demo credentials sets session and redirects to `/profile`.
6. Navigation links reflect logged-in state (`Profile`, `Logout`).
7. `GET /logout` clears session and redirects to `/login`.
8. Navigation links revert to logged-out state (`Sign in`, `Get started`).

### Manual Verification
1. Open browser to `/login`.
2. Test invalid login and verify error message and email preservation.
3. Test logging in with `demo@spendly.com` and `demo123`.
4. Confirm navigation shows `Profile` and `Logout`.
5. Click `Logout` and confirm redirection to `/login` and navigation reverted.
