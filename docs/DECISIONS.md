# Architecture Decision Log

Why we made the technical choices we did.

---

## ADR-001: Flask over FastAPI or Django

**Decision:** Use Flask 3.1 as the web framework.

**Context:** We needed a lightweight HTTP API for a time-boxed hackathon. The service has no frontend, just JSON endpoints and a redirect route.

**Reasons:**
- Flask is minimal — no ORM, no admin, no migrations bundled in. We control exactly what we include.
- Flask + Peewee is a well-understood stack with little magic. Debugging is straightforward.
- FastAPI would have required adding async support throughout (Peewee is sync). That complexity wasn't worth it for this scope.
- Django was ruled out — its batteries-included philosophy adds overhead (migrations system, settings module, apps framework) that we don't need.

**Trade-offs accepted:**
- No async I/O. Under very high concurrency, gunicorn workers block on DB queries. Acceptable for hackathon scale.
- No automatic input validation (like FastAPI's Pydantic models). We validate manually where needed.

---

## ADR-002: Peewee ORM over SQLAlchemy or raw psycopg2

**Decision:** Use Peewee 3.17 as the ORM.

**Context:** We need to model three related tables (users, urls, events) and run queries with filters, joins, and bulk inserts.

**Reasons:**
- Peewee's API is small and easy to learn quickly. `Model.select().where(...).limit(n)` reads naturally.
- `DatabaseProxy` lets us initialize the database lazily (in `create_app()`), which plays well with Flask's application factory pattern and makes testing easy.
- `playhouse.shortcuts.model_to_dict` converts model instances to JSON-serializable dicts without boilerplate.
- `chunked()` from Peewee makes batch inserts of CSV data simple and efficient.
- SQLAlchemy is more powerful but has a steeper learning curve (Core vs ORM, session management, etc.) that would slow us down.

**Trade-offs accepted:**
- Peewee has no migration system. Schema changes require manual SQL or a `--reset` + reload. Acceptable for a hackathon where schema is stable.
- Less community support than SQLAlchemy for complex queries.

---

## ADR-003: uv over pip / Poetry / Pipenv

**Decision:** Use uv as the package and environment manager.

**Context:** We need fast, reproducible installs across dev machines and CI.

**Reasons:**
- `uv sync` installs all dependencies in seconds — significantly faster than pip or Poetry.
- `uv run <script>` automatically uses the correct virtual environment without activation.
- `.python-version` + `pyproject.toml` pins both the Python version and dependencies in one place.
- Works natively in GitHub Actions with `astral-sh/setup-uv`.

**Trade-offs accepted:**
- uv is relatively new (2024). Team members unfamiliar with it need a brief orientation (see README uv basics section).

---

## ADR-004: PostgreSQL over SQLite

**Decision:** Use PostgreSQL 16 as the database.

**Context:** The hackathon provides seed data in CSV form with tens of thousands of rows. The service will be load-tested with concurrent users.

**Reasons:**
- PostgreSQL handles concurrent reads/writes correctly. SQLite has writer-lock contention under concurrent load.
- The seed data (users, urls, events) has referential integrity (foreign keys with CASCADE). PostgreSQL enforces this reliably.
- Unique index on `urls.short_code` is critical for redirect performance. PostgreSQL's index performance at hackathon data volumes is well-proven.
- The hackathon environment provides PostgreSQL, so no extra infrastructure cost.

**Trade-offs accepted:**
- Requires PostgreSQL to be running locally for development (vs. SQLite's zero-setup). Mitigated by clear setup instructions and Docker option.

---

## ADR-005: Per-request DB connections over a connection pool

**Decision:** Open a new DB connection per request via Flask's `before_request` / `teardown_appcontext` hooks.

**Context:** Peewee's `DatabaseProxy` pattern and Flask's request lifecycle.

**Reasons:**
- Simple, correct, and the officially recommended Peewee + Flask pattern.
- Avoids connection leak bugs that are common with manual pool management.
- At hackathon scale (50 concurrent VUs in load tests), per-request connections do not exhaust PostgreSQL's default `max_connections = 100`.

**Trade-offs accepted:**
- Each request pays a TCP connection setup cost (~1ms). At higher scale (>200 concurrent users), a connection pool (e.g., PgBouncer) would be needed.

---

## ADR-006: Locust for load testing

**Decision:** Use Locust for load testing, with k6 as an alternative.

**Context:** We need to benchmark the API and record a baseline before optimizations.

**Reasons:**
- Locust is Python-native — the test scenarios (`locustfile.py`) are just Python classes. No new language to learn.
- Already in our `dev` dependency group via `pyproject.toml`.
- k6 is documented as an alternative for teams that prefer a JavaScript/Go-based tool with richer metrics output.

**Trade-offs accepted:**
- Locust's headless output is less rich than k6's (no built-in HTML report without the web UI). We capture results manually in `BASELINE.md`.
