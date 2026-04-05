# MLH PE Hackathon — URL Shortener API

A production-ready URL shortener service built with Flask, Peewee ORM, and PostgreSQL.

**Stack:** Python 3.13 · Flask 3.1 · Peewee ORM · PostgreSQL 16 · uv

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Load Testing](#load-testing)
- [Further Documentation](#further-documentation)

---

## Quick Start

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/) and PostgreSQL running locally.

```bash
# 1. Clone the repo
git clone <repo-url> && cd PE-Hackathon-2026

# 2. Install dependencies (creates .venv automatically)
uv sync --group dev

# 3. Create the database
createdb hackathon_db

# 4. Configure environment
cp .env.example .env   # edit if your DB credentials differ

# 5. Load seed data
uv run python scripts/load_pe_seed.py

# 6. Start the server
uv run run.py

# 7. Verify
curl http://localhost:5000/health
# → {"status":"ok"}
```

---

## Architecture

```
                         ┌─────────────────────────────────┐
                         │          Client / Browser        │
                         └────────────────┬────────────────┘
                                          │ HTTP
                                          ▼
                         ┌─────────────────────────────────┐
                         │         Flask Application        │
                         │                                  │
                         │  ┌──────────┐  ┌─────────────┐  │
                         │  │ API      │  │  Redirect   │  │
                         │  │ Blueprint│  │  Blueprint  │  │
                         │  │ /api/*   │  │  /s/<code>  │  │
                         │  └────┬─────┘  └──────┬──────┘  │
                         │       │                │         │
                         │  ┌────▼────────────────▼──────┐  │
                         │  │       Peewee ORM           │  │
                         │  │  User · Url · Event        │  │
                         │  └────────────────┬───────────┘  │
                         └───────────────────┼─────────────┘
                                             │
                                             ▼
                         ┌─────────────────────────────────┐
                         │         PostgreSQL 16            │
                         │                                  │
                         │  ┌────────┐ ┌──────┐ ┌───────┐  │
                         │  │ users  │ │ urls │ │events │  │
                         │  └────────┘ └──────┘ └───────┘  │
                         └─────────────────────────────────┘
```

### Data Model

```
users (1) ──< urls (1) ──< events
              urls has short_code (unique index) for fast redirect lookups
```

- **users** — account records (id, username, email, created_at)
- **urls** — shortened links (short_code → original_url, is_active flag, owner)
- **events** — click / interaction audit log (event_type, timestamp, details)

---

## API Reference

Base URL: `http://localhost:5000`

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status":"ok"}` — used by load balancers and CI smoke tests |
| GET | `/` | Service info and endpoint map |

**Example**
```bash
curl http://localhost:5000/health
# {"status": "ok"}
```

---

### Users

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/users` | List users |
| GET | `/api/users/<id>` | Get a single user by ID |

**Query Parameters — `GET /api/users`**

| Param | Type | Default | Max | Description |
|-------|------|---------|-----|-------------|
| `limit` | int | 100 | 500 | Number of records to return |

**Example**
```bash
curl "http://localhost:5000/api/users?limit=5"
```
```json
[
  {"id": 1, "username": "alice", "email": "alice@example.com", "created_at": "2024-01-01T00:00:00"},
  ...
]
```

**`GET /api/users/<id>`**
```bash
curl http://localhost:5000/api/users/1
```
Returns `404` with `{"error": "not_found"}` if the user does not exist.

---

### URLs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/urls` | List shortened URLs |
| GET | `/api/urls/<id>` | Get a single URL record by ID |

**Query Parameters — `GET /api/urls`**

| Param | Type | Default | Max | Description |
|-------|------|---------|-----|-------------|
| `limit` | int | 100 | 500 | Number of records to return |
| `user_id` | int | — | — | Filter by owner user ID |

**Example**
```bash
curl "http://localhost:5000/api/urls?user_id=1&limit=10"
```
```json
[
  {
    "id": 42,
    "user_id": 1,
    "short_code": "abc123",
    "original_url": "https://example.com/very/long/path",
    "title": "Example Page",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00"
  }
]
```

---

### Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/events` | List events |

**Query Parameters — `GET /api/events`**

| Param | Type | Default | Max | Description |
|-------|------|---------|-----|-------------|
| `limit` | int | 100 | 500 | Number of records to return |
| `url_id` | int | — | — | Filter events for a specific URL |

---

### Redirect

| Method | Path | Description |
|--------|------|-------------|
| GET | `/s/<short_code>` | Redirect to the original URL |

- Returns `302 Found` and redirects to `original_url` if the short code exists and `is_active = true`.
- Returns `410 Gone` with `{"error": "gone", "reason": "inactive"}` if the URL is deactivated.
- Returns `404` if the short code does not exist.

**Example**
```bash
curl -L http://localhost:5000/s/abc123
# Follows redirect to https://example.com/very/long/path
```

---

## Project Structure

```
PE-Hackathon-2026/
├── app/
│   ├── __init__.py          # App factory (create_app)
│   ├── csv_parse.py         # parse_bool / parse_dt helpers for seed loading
│   ├── database.py          # DatabaseProxy, BaseModel, per-request connection hooks
│   ├── models/
│   │   ├── __init__.py      # Re-exports User, Url, Event
│   │   ├── user.py          # User model
│   │   ├── url.py           # Url model (short_code index)
│   │   └── event.py         # Event model
│   └── routes/
│       ├── __init__.py      # register_routes() — wires blueprints to app
│       └── api.py           # api_bp (/api/*) and short_bp (/s/<code>)
├── scripts/
│   └── load_pe_seed.py      # Bulk-load PE/*.csv into Postgres (--reset flag)
├── loadtests/
│   ├── locustfile.py        # 50-VU load test scenario
│   └── BASELINE.md          # Recorded performance results
├── tests/
│   ├── test_health.py       # Smoke test: /health
│   └── test_csv_parse.py    # Unit tests for CSV parsing helpers
├── docs/
│   ├── DEPLOY.md            # Deployment guide and rollback procedures
│   ├── TROUBLESHOOTING.md   # Known issues and fixes
│   ├── RUNBOOKS.md          # Operational runbooks
│   ├── DECISIONS.md         # Architecture decision log
│   └── CAPACITY.md          # Capacity planning and limits
├── .env.example             # Environment variable template
├── .github/workflows/ci.yml # GitHub Actions CI (test on every push)
├── pyproject.toml           # Project metadata and dependencies
├── run.py                   # Entry point: uv run run.py
└── README.md                # This file
```

---

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_NAME` | `hackathon_db` | Yes | PostgreSQL database name |
| `DATABASE_HOST` | `localhost` | Yes | PostgreSQL host |
| `DATABASE_PORT` | `5432` | Yes | PostgreSQL port |
| `DATABASE_USER` | `postgres` | Yes | PostgreSQL user |
| `DATABASE_PASSWORD` | `postgres` | Yes | PostgreSQL password |
| `FLASK_DEBUG` | `false` | No | Enable Flask debug mode (never `true` in production) |

---

## Running Tests

```bash
uv run pytest -v
```

CI runs automatically on every push via GitHub Actions (see `.github/workflows/ci.yml`). It spins up a real PostgreSQL 16 container — no mocking.

---

## Load Testing

```bash
# Start the server first
uv run run.py

# Run 50 concurrent users for 60 seconds
uv run locust -f loadtests/locustfile.py \
  --host http://127.0.0.1:5000 \
  --users 50 --spawn-rate 50 --run-time 60s --headless
```

**Baseline results** (50 VUs, local dev server): ~85.6 RPS, p95 ~450ms, 0% error rate.
See `loadtests/BASELINE.md` for full results and a template for recording future runs.

---

## Further Documentation

| Doc | What's in it |
|-----|--------------|
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | How to deploy, rollback, and promote to production |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Bugs hit during the hackathon and how they were fixed |
| [`docs/RUNBOOKS.md`](docs/RUNBOOKS.md) | Step-by-step operational runbooks for common alerts |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Why Flask, Peewee, uv — the reasoning behind each choice |
| [`docs/CAPACITY.md`](docs/CAPACITY.md) | How many users can we handle? Where are the limits? |
