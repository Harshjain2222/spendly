# Implementation Plan: Profile Page Design (with Frontend Design Skill)

## Goal Description
Implement the user profile page (`/profile`) for Spendly as specified in [04-profile-page-design.md](file:///c:/Users/DELL/Downloads/expense-tracker/.claude/specs/04-profile-page-design.md), enhanced with the design principles from the [spendly-ui-designer skill](file:///c:/Users/DELL/Downloads/expense-tracker/.claude/skills/frontend-design/SKILL.md).

Currently, `/profile` is a placeholder text stub. This plan replaces it with a modern, production-grade fintech profile screen featuring card-based composition, Lucide icons, tabular numbers for monetary metrics, generous spacing on an 8px grid, and strict adherence to Spendly CSS variables.

---

## User Review Required

> [!IMPORTANT]
> **Lucide Icons via CDN in `base.html`:**
> Following the `spendly-ui-designer` skill guidelines, Lucide icons will be loaded via CDN script tag in `templates/base.html` (`https://unpkg.com/lucide@latest`) and initialized in `static/js/main.js` via `lucide.createIcons()`.

> [!NOTE]
> **Fintech Design System Principles Applied:**
> - **Card Surfaces:** Grouped in distinct card surfaces (`--paper-card`) with subtle borders (`--border`) and micro-shadows.
> - **Tabular Figures:** Numbers and currency amounts use `font-variant-numeric: tabular-nums` for clean visual alignment.
> - **Typography & Colors:** DM Serif Display for headings, DM Sans for body/labels, and strict usage of CSS variables (zero hardcoded hex values).

---

## Open Questions

None. The requirements and design language are fully aligned.

---

## UI Plan (Spendly UI Designer)

1. **Header Profile Card**:
   - Left: Rounded accent initials avatar (`--accent` background, `--paper` bold text).
   - Center: User's full name, email address, and a subtle pill badge indicating "Member since <Date>".
   - Right: Quick sign-out action button with a `log-out` icon and subtle danger hover styling.
2. **Fintech Metrics Row (3-up card grid)**:
   - **Total Spending Card**: Lifetime spending amount in `₹` with `wallet` icon and tabular figures.
   - **Expenses Logged Card**: Total count of recorded transactions with `receipt` icon.
   - **Account Status Card**: "Active" status indicator with `shield-check` icon and green status dot.
3. **Account Information Card**:
   - Structured key-value rows with subtle dividers and metadata icons (`user`, `mail`, `calendar`, `hash`).
   - Displays: Full Name, Email Address, Registration Date, Account ID.
4. **Navigation Actions**:
   - Secondary button: "Back to Home" (`arrow-left` icon).
   - Danger outline button: "Sign out" (`log-out` icon).

---

## Proposed Changes

### Component 1 — Backend Route Handler
- Modify [`app.py`](file:///c:/Users/DELL/Downloads/expense-tracker/app.py):
  - Protect `GET /profile` with session check (`user_id`).
  - Query user record from `users` table via `get_db()`.
  - Handle missing user by purging session and redirecting to `login`.
  - Query aggregate expense metrics (`COUNT(*)` and `SUM(amount)`).
  - Compute initials and formatted `member_since` date.
  - Render `templates/profile.html`.

### Component 2 — Frontend Templates & Icons
- Modify [`templates/base.html`](file:///c:/Users/DELL/Downloads/expense-tracker/templates/base.html) to include Lucide CDN.
- Modify [`static/js/main.js`](file:///c:/Users/DELL/Downloads/expense-tracker/static/js/main.js) to initialize `lucide.createIcons()`.
- Create [`templates/profile.html`](file:///c:/Users/DELL/Downloads/expense-tracker/templates/profile.html) with fintech card composition and Lucide icons.

### Component 3 — Stylesheet & Fintech Polish
- Modify [`static/css/style.css`](file:///c:/Users/DELL/Downloads/expense-tracker/static/css/style.css):
  - Append scoped profile styling based on 8px grid.
  - Use `font-variant-numeric: tabular-nums` for currency values.
  - Subtle fintech card shadow and soft borders.
  - Strict adherence to CSS variables without hex colors.
  - Mobile responsiveness.

---

## Verification Plan

### Automated Tests
Run test script verifying:
1. Unauthorized `/profile` redirects to `/login`.
2. Invalid session purges session and redirects to `/login`.
3. Valid authenticated user renders 200 with name, email, initials, total spent, and Lucide icon attributes.
4. CSS lint confirms no hardcoded hex colors.

### Manual Verification
1. Start app and visit `/profile` logged out → redirected to `/login`.
2. Log in with user credentials → lands on `/profile`.
3. Verify visual card layout, Lucide icons, tabular numbers, and responsive behavior.
4. Click Sign out → session terminates cleanly.
