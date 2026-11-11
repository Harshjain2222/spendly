# Spendly: AI-Powered Expense Tracker

A multi-user expense tracker with a Flask website and an AI chat assistant. Users log in, manage expenses through the normal website, or simply type things like *"Add 200 for lunch today"* or *"Summarize this month by category"* in the chat page.

The chatbot talks to a separate **MCP (Model Context Protocol) server** that reads and writes the same **PostgreSQL (Neon)** database, with strict per-user isolation.

---

## Features

- User registration and login (hashed passwords, session-based auth)
- Add, edit, delete and view expenses on the website
- AI chat page: add, list, summarize and edit expenses in plain English
- Fixed category list, validated on the server
- Per-user data isolation, enforced at the database query level
- Persistent cloud database (Neon PostgreSQL) with schema migrations
- Guardrails: expense-only assistant, rate limits, input validation

---

## Architecture

```
Browser (website + chat page)
        |
        v
Flask app (login, sessions, DB access, /chat)
        |  1. reads user id from the session
        |  2. signs a 15-minute JWT for that user
        v
chat_client.py  --->  LLM (Groq) with MCP tools
        |
        v
MCP server (FastMCP, hosted on Railway)
        |  verifies the JWT, takes user_id from it
        v
Neon PostgreSQL  <---  Flask also reads/writes the same database
```

**Key idea:** the user id is never taken from the chat message, the request body, or the LLM. It comes from the logged-in session, travels inside a signed token, and is applied as `WHERE user_id = ...` in every query. No tool has a `user_id` parameter.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Website | Flask, Jinja2 templates, custom CSS/JS |
| Database | PostgreSQL on Neon |
| ORM and migrations | Flask-SQLAlchemy, Flask-Migrate (Alembic) |
| Auth | Session login, Werkzeug password hashing, PyJWT for service tokens |
| MCP server | FastMCP, asyncpg |
| LLM client | LangChain (`langchain-mcp-adapters`, `langchain-openai`) with Groq |
| Rate limiting | Flask-Limiter |
| Hosting | Railway (MCP server), website host of your choice |

---

## Project Structure

This project is two deployable parts.

```
website/                    # Flask app
├── app.py                  # routes, sessions, /chat endpoints, rate limiter
├── chat_client.py          # LLM + MCP client, token creation
├── database/               # models, queries, DB init
├── migrations/             # Alembic migration history (commit this)
├── templates/              # base.html, chat.html, ...
├── static/                 # css, js
├── requirements.txt
└── .env.example

mcp-server/                 # separate deployment
├── main.py                 # FastMCP tools + JWT verification
├── requirements.txt
└── .env.example
```

---

## Database Schema

**users**

| Column | Type |
|---|---|
| id | integer, primary key |
| name | text, not null |
| email | text, unique, not null |
| password_hash | text, not null |
| created_at | timestamp |

**expenses**

| Column | Type |
|---|---|
| id | integer, primary key |
| user_id | integer, foreign key to users.id, indexed |
| amount | numeric(12,2) |
| category | text |
| date | date |
| description | text |
| created_at | timestamp |

**Categories:** Food, Transport, Bills, Health, Entertainment, Shopping, Education, investments, Other

---

## MCP Tools

| Tool | Purpose |
|---|---|
| `add_expense` | Add an expense (amount, category, date, description) |
| `list_expenses` | List expenses in a date range |
| `summarize` | Totals by category in a date range |
| `update_expense` | Edit an expense by id (own expenses only) |

There is intentionally **no delete tool**. Deleting is done on the website.

---

## Environment Variables

### Website (`website/.env`)

```
SECRET_KEY=long_random_string
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
JWT_SECRET=long_random_string_same_as_mcp_server
MCP_URL=https://YOUR-MCP-SERVER.up.railway.app/mcp
GROQ_API_KEY=your_groq_key
LLM_MODEL=openai/gpt-oss-20b
```

### MCP server (`mcp-server/.env` or Railway variables)

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST-pooler/DBNAME?sslmode=require
JWT_SECRET=long_random_string_same_as_website
```

Notes:

- `JWT_SECRET` must be **identical** in both places.
- For the MCP server (asyncpg), remove `&channel_binding=require` from the Neon URL.
- Generate secrets with:
  ```
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- Never commit `.env` files.

---

## Local Setup

### 1. Database

1. Create a project on [Neon](https://neon.tech) and copy the connection string.
2. Put it in `DATABASE_URL` in the website `.env`.

### 2. Website

```bash
cd website
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
flask db upgrade
python app.py
```

Open `http://localhost:5001`, register, log in, and use the **Chat** link in the navbar.

### 3. MCP server

```bash
cd mcp-server
pip install -r requirements.txt
python main.py
```

For local testing, set `MCP_URL=http://localhost:8000/mcp` in the website `.env`.

---

## Deployment

### MCP server (Railway)

1. Push `mcp-server/` to GitHub and create a Railway service from the repo.
2. Add variables: `DATABASE_URL`, `JWT_SECRET`.
3. In Settings, then Networking, generate a public domain pointing to the port the app logs on startup (Railway sets `PORT`).
4. Your MCP URL is `https://<domain>/mcp`.

Pushing to the connected branch triggers an automatic redeploy.

### Website

1. Push `website/` to GitHub and create a service on Railway, Render, or similar.
2. Start command:
   ```
   gunicorn app:app --timeout 120
   ```
3. Add all website environment variables.
4. Run `flask db upgrade` once against the production database.
5. Serve only over HTTPS.

---

## Security Design

- **Identity from the session only.** The browser sends `{message, history}`, never a user id.
- **Signed, short-lived tokens.** Flask signs a 15-minute HS256 JWT. The MCP server requires `exp` and `sub`.
- **Query-level isolation.** Every SQL statement filters by `user_id`, including updates.
- **No user id parameter** on any MCP tool, so the LLM cannot choose whose data to touch.
- **Parameterized queries** only, with server-side validation of amounts, dates and categories.
- **Rate limiting:** 20 chat requests per minute per user (plus a daily cap).
- **Input limits:** message max 1000 characters, history max 10 messages, max 5 tool rounds per request.
- **Guardrails:** expense-only system prompt and output token cap.
- **Secrets** live only in environment variables.

### Production checklist

- [ ] `.env` is in `.gitignore` and was never committed
- [ ] `SECRET_KEY` and `JWT_SECRET` are long and random
- [ ] `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_SECURE=True`
- [ ] `debug=False`, running behind Gunicorn over HTTPS
- [ ] `/login` is rate-limited
- [ ] `test.py` or any token-forging script is not deployed
- [ ] `migrations/` folder is committed

If `JWT_SECRET` ever leaks, generate a new one and update it on both services immediately.

---

## Testing Checklist

1. Logged-out `GET /chat` redirects to login; logged-out `POST /chat/message` is rejected.
2. "Add 50 for tea today" creates a row for the logged-in user.
3. "Show my expenses this month" shows only that user's rows.
4. A second user cannot see the first user's expenses.
5. A 1001-character message returns 400.
6. A wrong `JWT_SECRET` results in "Session expired" and no data is written.
7. "Write a prime number program" gets the refusal message.

---

## Troubleshooting

| Problem | Likely cause |
|---|---|
| `KeyError: JWT_SECRET` or `DATABASE_URL` | Variable missing in `.env` or in the host's dashboard |
| Tool returns "Unauthorized" | `JWT_SECRET` differs between website and MCP server, or token expired |
| 502 on the MCP domain | Public domain points to the wrong port |
| 404 on the MCP URL | Missing `/mcp` at the end |
| Foreign key error on insert | Token `sub` is not a real `users.id` |
| Connection or SSL error to Neon | `channel_binding` still in the URL, or wrong password |
| Old behavior after changing code | Push did not reach the branch Railway watches, or the client points to an old service |
| `flask db upgrade` fails with "Can't locate revision" | `migrations/` folder was deleted or is out of sync |

---

## Roadmap

- Budgets per category with alerts
- Monthly charts and spending trends
- Chat history saved per user
- Delete and undo with confirmation in chat
- Export to CSV
- Asymmetric token signing (RS256) so the MCP server only holds a public key

---

## License

Add your preferred license here (for example MIT).
