# Troubleshooting

Common problems encountered during the hackathon and how to fix them.

---

## Database Connection

### `peewee.OperationalError: could not connect to server`

**Symptoms:** Server crashes on startup or first request with a Peewee connection error.

**Causes and fixes:**

| Cause | Fix |
|-------|-----|
| PostgreSQL is not running | `brew services start postgresql` (macOS) or `sudo systemctl start postgresql` (Linux) |
| Wrong credentials in `.env` | Check `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT` match your Postgres config |
| Database does not exist | `createdb hackathon_db` (or whatever `DATABASE_NAME` is set to) |
| Port conflict | `lsof -i :5432` — kill any other process using the port |

---

### `psycopg2.errors.UndefinedTable: relation "users" does not exist`

The tables haven't been created yet.

```bash
uv run python scripts/load_pe_seed.py
```

If the tables exist but are empty (e.g., seed was not loaded):

```bash
uv run python scripts/load_pe_seed.py --reset
```

---

### `FATAL: role "postgres" does not exist`

Your PostgreSQL install uses a different default superuser (common on macOS with Homebrew).

```bash
# Find your actual superuser
psql -l

# Update .env to match
DATABASE_USER=<your-actual-superuser>
```

---

## Seed Loading

### `Missing seed file: PE/users.csv`

The `PE/` directory with CSV files is not present. Download it from the MLH PE Hackathon platform and place it at the repo root:

```
PE-Hackathon-2026/
└── PE/
    ├── users.csv
    ├── urls.csv
    └── events.csv
```

---

### `peewee.IntegrityError: duplicate key value violates unique constraint`

The data was already loaded. Use `--reset` to wipe and reload:

```bash
uv run python scripts/load_pe_seed.py --reset
```

---

## Application

### `ImportError: No module named 'app'`

You are running a script from a directory other than the repo root, or the virtual environment is not active.

```bash
# Always run from repo root using uv
cd /path/to/PE-Hackathon-2026
uv run run.py
```

---

### `GET /s/<short_code>` returns 404 but the code exists in the DB

Check that `is_active` is `true` for that URL:

```bash
psql -U postgres -d hackathon_db \
  -c "SELECT id, short_code, is_active FROM urls WHERE short_code = 'abc123';"
```

If `is_active = false`, the redirect returns `410 Gone` (not 404). The short code itself not existing returns 404.

---

### Flask dev server shows `Address already in use`

Something else is on port 5000.

```bash
lsof -i :5000          # find what's using it
kill -9 <PID>          # kill it
uv run run.py          # restart
```

---

## Tests

### `pytest` fails with `peewee.OperationalError`

Tests hit the real database (no mocking). Make sure PostgreSQL is running and `.env` is configured correctly before running tests.

```bash
# Confirm the DB is reachable
psql -U postgres -d hackathon_db -c "SELECT 1;"
uv run pytest -v
```

---

### CI passes locally but fails in GitHub Actions

Check that all environment variables are set correctly in the workflow file (`.github/workflows/ci.yml`). The workflow sets `DATABASE_*` env vars explicitly — if you add new required vars, add them there too.

---

## Load Testing

### Locust shows high failure rate on first run

The seed data may not be loaded. API endpoints that query empty tables return empty arrays (200), but `GET /s/<short_code>` will 404 for any short code if the `urls` table is empty.

```bash
uv run python scripts/load_pe_seed.py
```

### p95 latency is much higher than baseline (~450ms)

Possible causes:

| Cause | Fix |
|-------|-----|
| Running on Flask dev server | Use gunicorn in production (`--workers 4`) |
| Missing DB index on `short_code` | Already indexed in the schema; if dropped, recreate: `CREATE UNIQUE INDEX ON urls (short_code);` |
| Too many concurrent connections | Reduce `--users` in locust, or add a connection pool |
| Postgres running out of `max_connections` | Check `SHOW max_connections;` in psql; default is 100 |
