# Spec: Registration

## Overview
Implement the user registration feature for Spendly, allowing new users to create an account by submitting their full name, email address, and a secure password. Following the database foundation in Step 01, this feature establishes user identity in the database, enabling authentication before login, session management, and personalized expense tracking are introduced.

## Depends on
Step 01: Database Setup (`users` table schema, `get_db()` connection helper, and database bootstrap in `app.py`).

## Routes
- `GET /register` — Display the registration form — public
- `POST /register` — Process registration submission, validate inputs, create new user account, and redirect to login — public

## Database changes
No database changes.

## Templates
- **Create:** None
- **Modify:**
  - `templates/register.html` — Ensure form preserves submitted name and email values on validation errors and displays error messages (`{{ error }}`).

## Files to change
- `app.py` — Update `/register` route to support `POST` method alongside `GET`, perform input validation (presence of all fields, valid email format, minimum 8 character password), check for duplicate email, hash password using Werkzeug, insert user record into SQLite using `get_db()`, and redirect to `/login`.
- `templates/register.html` — Update input fields to retain user input (`name`, `email`) if registration validation fails.

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
- Validate that `name`, `email`, and `password` are present and non-empty.
- Enforce a minimum password length of 8 characters.
- Check if the email already exists in `users` table before insert (or catch unique constraint violation) and return a user-friendly error message ("Email already registered").
- Hash passwords using `werkzeug.security.generate_password_hash`.
- On successful registration, redirect to `/login`.
- On validation or duplicate email failure, re-render `register.html` with an `error` message and pre-fill existing `name` and `email` values without retaining the password.

## Definition of done
- [x] Navigating to `GET /register` renders the registration form with Name, Email, and Password inputs.
- [x] Submitting empty fields displays a validation error and prevents account creation.
- [x] Submitting a password shorter than 8 characters displays an error indicating minimum length requirement.
- [x] Submitting an existing email (e.g. `demo@spendly.com`) shows an error stating that the email is already registered.
- [x] Submitting valid registration details creates a new row in the `users` table in SQLite.
- [x] The stored password in the database is verified to be a hashed string (via Werkzeug), not plain text.
- [x] Successful registration redirects the user to `/login`.
- [x] When a registration error occurs, the user-submitted name and email values are preserved in the form fields.
