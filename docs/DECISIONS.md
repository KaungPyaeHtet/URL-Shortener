# Architecture Decision Log

Why we made the technical choices we did.

---
## ADR-001: Per-request DB connections over a connection pool

**Decision:** Open a new DB connection per request via Flask's `before_request` / `teardown_appcontext` hooks.

**Context:** Peewee's `DatabaseProxy` pattern and Flask's request lifecycle.

**Reasons:**
- Simple, correct, and the officially recommended Peewee + Flask pattern.
- Avoids connection leak bugs that are common with manual pool management.
- At hackathon scale (50 concurrent VUs in load tests), per-request connections do not exhaust PostgreSQL's default `max_connections = 100`.

**Trade-offs accepted:**
- Each request pays a TCP connection setup cost (~1ms). At higher scale (>200 concurrent users), a connection pool (e.g., PgBouncer) would be needed.