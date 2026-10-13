# Spec: Login and Logout

## Overview
Implement session-based user authentication enabling registered users to sign in and sign out of Spendly securely. Following the database foundation in Step 01 and account registration in Step 02, this feature verifies user credentials with `werkzeug.security.check_password_hash`, initializes signed session state upon successful authentication, updates the site navigation dynamically based on authentication status, and provides a logout mechanism to terminate active sessions safely.

## Depends on
- Step 01: Database Setup (`users` table schema, `get_db()` helper)
- Step 02: Registration (`/register` route, password hashing with `generate_password_hash`)

## Routes
- `GET /login` — Display the sign-in form — public
- `POST /login` — Validate credentials against database, set session, and redirect — public
- `GET /logout` — Clear active user session and redirect to login page — logged-in

## Database changes
No database changes.

## Templates
- **Create:** None
- **Modify:**
  - `templates/login.html` — Preserve entered `email` on authentication failure and display error messages (`{{ error }}`).
  - `templates/base.html` — Conditionally display navigation links based on user authentication state (`session.get('user_id')`), showing Profile and Logout when logged in, or Sign in and Get started when logged out.

## Files to change
- `app.py` — Configure session secret key (`app.secret_key`), update `/login` route to handle `POST` method with credential verification using `check_password_hash`, store `user_id` and `user_name` in `session`, and update `/logout` to clear session and redirect to `/login`.
- `templates/login.html` — Update email input to retain user value (`value="{{ email or '' }}"`) upon login failure.
- `templates/base.html` — Update `.nav-links` block to render authenticated navigation (`Profile`, `Logout`) or guest navigation (`Sign in`, `Get started`) based on `session.get('user_id')`.

## Files to create
None

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Configure `app.secret_key` to support Flask signed session cookies.
- Validate that both email and password are provided upon form submission.
- Normalize email to lowercase and strip whitespace before database query.
- Use parameterized query `SELECT id, name, email, password_hash FROM users WHERE email = ?` via `get_db()`.
- Verify passwords using `werkzeug.security.check_password_hash`.
- Return a generic error message ("Invalid email or password.") on invalid credentials to avoid username enumeration.
- Set `session["user_id"]` and `session["user_name"]` on successful authentication.
- Preserve entered `email` value on failure, but never preserve the submitted password.
- Clear session using `session.clear()` on `/logout` and redirect to `/login`.
- If an already authenticated user accesses `GET /login` or `GET /register`, redirect them to `/profile`.

## Definition of done
- [x] Navigating to `GET /login` renders the login page with email and password inputs.
- [x] Submitting empty email or password displays an error message preventing login.
- [x] Submitting an unregistered email displays "Invalid email or password.".
- [x] Submitting a registered email with an incorrect password displays "Invalid email or password.".
- [x] On login failure, the submitted email is preserved in the form input and the password field is cleared.
- [x] Submitting valid credentials (e.g. `demo@spendly.com` / `demo123`) authenticates the user and sets session `user_id` and `user_name`.
- [x] Successful login redirects the user to `/profile`.
- [x] When logged in, the navigation bar displays `Profile` and `Logout` instead of `Sign in` and `Get started`.
- [x] Navigating to `/logout` clears the user session and redirects to `/login`.
- [x] After logging out, the navigation bar reverts to displaying `Sign in` and `Get started`.
