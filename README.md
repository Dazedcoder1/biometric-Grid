# GridSphere — Biometric Attendance & Task Manager

Two folders, **one** environment file, one database.

```
.env         the only environment file — backend and frontend both read it
backend/     FastAPI + SQLAlchemy + Alembic
frontend/    React 19 + Vite
```

The database is **Neon** (hosted Postgres). There is nothing to install or start
locally for it — everyone points at the same connection string.

---

## First-time setup

### 1. The environment file

```powershell
copy .env.example .env
```

One file at the repository root serves both sides. The backend finds it by
walking up from `app/core/config.py`, so `uvicorn`, `alembic` and the seed
script all read it whichever folder you launch them from; the frontend finds it
because `vite.config.js` sets `envDir` to the same place.

Only keys prefixed `VITE_` are compiled into the browser bundle. `DATABASE_URL`,
`JWT_SECRET_KEY` and the rest sit in the same file and never leave the server.

Fill in three things:

| Key | Where it comes from |
|---|---|
| `DATABASE_URL` | Neon Console → your project → **Connect** → copy the connection string. Paste it verbatim, `?sslmode=require` included. |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `GITHUB_ENC_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

You do **not** need to reshape the Neon URL by hand. `app/db/url.py` converts it
to the asyncpg form, attaches TLS, and disables prepared statements on the
`-pooler` endpoint at startup.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python seed_test_accounts.py     # test accounts + sample tasks
```

`seed_test_accounts.py` is idempotent and will tell you it is writing to a
remote database before it does. Run it once for the team, not once per person.

### 3. Frontend

```powershell
cd ..\frontend
npm install
```

No environment file of its own — it reads the root `.env`. The line that matters
is already there:

```ini
VITE_API_BASE_URL=http://localhost:8000
```

Without it the app talks to the **production** API. Vite reads the file only at
startup — restart `npm run dev` after any change to it.

---

## Running it

Two terminals.

```powershell
# backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

```powershell
# frontend
cd frontend
npm run dev
```

| URL | What |
|---|---|
| http://localhost:5173 | The application |
| http://localhost:8000/docs | Interactive API documentation |

---

## Test accounts

Three separate login pages — signing in at the wrong one will not work.

| Role | Page | Credentials |
|---|---|---|
| Tenant Admin | `/login/tenant` | API key `test-tenant-key-0000000000000000` (no password) |
| Org Admin | `/login/org` | `orgadmin@test.local` / `OrgAdmin@123` |
| Employee | `/login/employee` | `employee@test.local` … `employee5@test.local`, or `EMP001`–`EMP005` / `Employee@123` |

Development credentials. They live in the repository in plain text — never seed
them against a production database.

---

## The environment file

Exactly one, at the repository root, gitignored, with a committed
`.env.example` beside it.

| Side | How it finds the file | What it sees |
|---|---|---|
| Backend | `app/core/config.py` walks up from itself to the first `.env` | everything |
| Frontend | `vite.config.js` sets `envDir` to the same folder | only `VITE_*` |

Two rules:

- **Never put a secret in a `VITE_` key.** Those are compiled into the browser
  bundle and are readable by anyone who opens the site.
- **Add a key to `.env` and to `.env.example` in the same commit**, or the next
  person to clone gets a server that will not boot.

Do not create a `.env` inside `backend/` or `frontend/`. Both sides stop at the
first `.env` they find on the way up, so a stray one silently shadows the real
file — and you get a config that works for one person and nobody else.

---

## Notes on Neon

- **Compute suspends after ~5 minutes idle.** The first request after a pause
  takes a second or two while it wakes. The connection pool is configured with
  `pool_pre_ping` and `pool_recycle=280` so suspended sockets are retired rather
  than handed to a request.
- **Use the `-pooler` endpoint** for the app. It is PgBouncer in transaction
  mode, which cannot hold prepared statements — handled automatically in
  `app/db/url.py`.
- **Branching.** Neon can branch a database like Git. If you need to test a
  destructive migration, branch it rather than running it against the shared
  database.
- **One database, shared.** Someone else's seed run resets your test passwords.
  That is the trade for having no local database to maintain.

## Where to look when something breaks

- The backend terminal — the **last** line before the traceback names the real
  problem; everything above it is framework plumbing.
- `backend/SETUP.md` — the GitHub task-sync integration in depth.
- http://localhost:8000/docs — every endpoint, live.
