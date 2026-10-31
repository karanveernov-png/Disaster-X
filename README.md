# TaskFlow API — FastAPI + Supabase

Converted from Flask + SQLite to **FastAPI** (async) + **Supabase** (PostgreSQL).

## Stack

| Layer | Original | New |
|---|---|---|
| Framework | Flask | FastAPI + uvicorn |
| Database | SQLite (sqlite3) | Supabase (PostgreSQL via asyncpg) |
| ORM / SQL | Raw sqlite3 | SQLAlchemy Core (async text queries) |
| Auth | PyJWT + Werkzeug | python-jose + passlib/bcrypt |
| Validation | Manual | Pydantic v2 + pydantic-settings |
| Config | Custom `.env` loader | `pydantic-settings` BaseSettings |

---

## Quick Start

### 1. Create Supabase project

1. Go to [supabase.com](https://supabase.com) → New project
2. Dashboard → **SQL Editor** → paste and run `migrations/001_initial_schema.sql`
3. Dashboard → **Project Settings → API** → copy your keys

### 2. Configure environment

```bash
cp .env.example .env
# Fill in: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
# Fill in: DATABASE_URL (Transaction pooler string from Supabase settings)
# Generate: python -c "import secrets; print(secrets.token_hex(32))"  → SECRET_KEY
```

### 3. Install & run

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

---

## Project Structure

```
taskflow_fastapi/
├── app/
│   ├── main.py                      # FastAPI app factory + lifespan
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py          # Mounts all routers at /api/v1
│   │       └── endpoints/
│   │           ├── auth.py          # /auth/register, login, refresh, logout, me
│   │           ├── users.py         # /users/me  (GET, PATCH, DELETE)
│   │           ├── projects.py      # /projects  (CRUD)
│   │           └── tasks.py         # /projects/{id}/tasks  (CRUD)
│   ├── core/
│   │   ├── config.py                # pydantic-settings — reads .env
│   │   ├── exceptions.py            # Domain exception hierarchy
│   │   ├── security.py              # JWT (python-jose) + bcrypt (passlib)
│   │   └── logging.py              # Structured logging setup
│   ├── db/
│   │   └── database.py              # AsyncEngine + Supabase SDK client
│   ├── middleware/
│   │   ├── auth.py                  # get_current_user FastAPI dependency
│   │   └── error_handlers.py        # AppError → JSON response mapping
│   ├── schemas/
│   │   └── __init__.py              # All Pydantic request/response models
│   └── services/
│       ├── base.py                  # Async paginate, row helpers
│       ├── auth_service.py          # Login, refresh, logout, token validation
│       ├── user_service.py          # User CRUD
│       ├── project_service.py       # Project CRUD (owner-scoped)
│       └── task_service.py          # Task CRUD (project-scoped)
├── migrations/
│   └── 001_initial_schema.sql       # Run in Supabase SQL Editor
├── requirements.txt
├── .env.example
└── README.md
```

---

## API Reference

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Rotate token pair |
| POST | `/api/v1/auth/logout` | Revoke refresh token |
| GET  | `/api/v1/auth/me` | Current user info |

### Users
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/users/me` | Get profile |
| PATCH | `/api/v1/users/me` | Update name / password |
| DELETE | `/api/v1/users/me` | Deactivate account |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/projects` | List projects (`?page=1&page_size=20`) |
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects/{id}` | Get project |
| PATCH | `/api/v1/projects/{id}` | Update project |
| DELETE | `/api/v1/projects/{id}` | Delete project + cascade tasks |

### Tasks
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/projects/{id}/tasks` | List tasks (filter: `status`, `priority`, `assignee_id`) |
| POST | `/api/v1/projects/{id}/tasks` | Create task |
| GET | `/api/v1/projects/{id}/tasks/{task_id}` | Get task |
| PATCH | `/api/v1/projects/{id}/tasks/{task_id}` | Update task |
| DELETE | `/api/v1/projects/{id}/tasks/{task_id}` | Delete task |

---

## Supabase Notes

### Two access patterns in `app/db/database.py`

**SQLAlchemy async sessions** (used by all services) — full SQL control:
```python
async with get_session_factory()() as session:
    result = await session.execute(sa.text("SELECT * FROM tasks WHERE ..."), params)
```

**Supabase SDK** — useful for Storage, Realtime, or PostgREST shortcuts:
```python
supabase = get_supabase()
data = supabase.table("tasks").select("*").eq("project_id", pid).execute()
```

### Row Level Security
The migration enables RLS on all tables. The backend uses the **service role key**
which bypasses RLS — this is intentional for server-side code. The anon key
(respects RLS) is available via `get_supabase_anon()` if you want to enforce
per-user policies at the DB level too.

### Token cleanup
Call `sweep_expired_blocklist_entries(session)` periodically, or use the
built-in Supabase `pg_cron` extension to schedule:
```sql
SELECT cron.schedule('sweep-tokens', '0 * * * *', 'SELECT sweep_expired_tokens()');
```

---

## Key Changes from Flask Version

| Flask | FastAPI |
|-------|---------|
| `@app.route(...)` | `@router.get/post/patch/delete(...)` |
| `g.db` (thread-local) | `Depends(get_db)` (async session per request) |
| `request.json` | Pydantic body model auto-parsed |
| `jsonify(...)` + status | `response_model=` + return dict |
| Manual `@require_auth` decorator | `Depends(get_current_user)` |
| `sqlite3.Connection` everywhere | `AsyncSession` everywhere |
| `Config.validate()` on startup | pydantic-settings raises on import |
| `conn.execute(sql, (?,?,?))` | `session.execute(text(sql), {k: v})` |
