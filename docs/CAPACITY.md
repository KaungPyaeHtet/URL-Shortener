# Capacity Plan

How many users can we handle? Where are the limits?

---

## Measured Baseline

Tested on a local Flask dev server (single-threaded, no gunicorn):

| Metric | Value |
|--------|-------|
| Concurrent users (VUs) | 50 |
| Requests per second (RPS) | ~85.6 |
| Avg latency | ~331ms |
| p50 latency | ~330ms |
| p95 latency | ~450ms |
| p99 latency | ~610ms |
| Error rate | 0% |

> **Note:** These numbers are from the Flask dev server. Production gunicorn with multiple workers will perform significantly better.

---

## Estimated Production Capacity

### Single server (2-core VPS, gunicorn 5 workers)

| Scenario | Estimated RPS | p95 Latency | Notes |
|----------|---------------|-------------|-------|
| Health / index only | ~500–800 | < 50ms | Near-zero DB work |
| Mixed read endpoints | ~300–500 | ~100–200ms | DB queries with indexes |
| Redirect (`/s/<code>`) | ~400–600 | ~80–150ms | Single indexed lookup |

Gunicorn rule of thumb: `2 × cores + 1` workers = 5 workers on a 2-core machine. Each worker handles one request at a time. Under I/O wait (DB query), the OS can context-switch, but true concurrency is limited.

---

## Bottlenecks and Limits

### 1. PostgreSQL `max_connections` (default: 100)

Each gunicorn worker opens one DB connection per active request. With 5 workers and 50 concurrent users, peak connections are well within the default 100 limit.

**Limit hits when:** concurrent users × gunicorn workers approaches 100.
**Fix:** Add PgBouncer (connection pooler) in front of PostgreSQL. This allows thousands of app connections to multiplex over a small pool of actual DB connections.

### 2. Gunicorn worker count

Synchronous workers block on DB I/O. With 5 workers, you can serve ~5 requests simultaneously.

**Limit hits when:** RPS × avg_latency_seconds > worker_count (Little's Law).
- At 300ms avg, 5 workers → max ~16 RPS before queuing.
- At 100ms avg, 5 workers → max ~50 RPS before queuing.

**Fix:** Increase workers (up to ~`2 × cores + 1`), or switch to async workers (`gevent` or `uvicorn` + async Flask) for I/O-bound workloads.

### 3. Database query performance

All read endpoints use `ORDER BY id LIMIT n`. Without indexes beyond the primary key, large tables will slow down filtered queries.

**Current indexes:**
- `urls.short_code` — unique index (critical for redirect performance)
- `urls.id` — primary key
- `events.event_type` — index (defined in model)

**Limit hits when:** Table size grows beyond millions of rows without query-specific indexes.
**Fix:** Add indexes for common filter patterns (e.g., `(user_id, id)` on `urls` if `/api/urls?user_id=` is a hot path).

### 4. Single-server disk I/O (PostgreSQL WAL + data files)

At sustained high write rates (bulk seed loads or heavy event logging), disk throughput becomes the limit.

**Limit hits when:** Disk write throughput is saturated.
**Fix:** Move PostgreSQL to a dedicated database server with SSD storage; or use a managed DB (e.g., Neon, Supabase).

---

## Scaling Path

```
Current (dev server, 1 process)
    ↓ 10× improvement
Production (gunicorn, 4–8 workers) → handles ~200–400 concurrent users
    ↓ 10× improvement
Add PgBouncer + read replicas → handles ~2,000–4,000 concurrent users
    ↓ 10× improvement
Horizontal scaling (multiple app servers behind load balancer) → handles ~20,000+ concurrent users
```

---

## Quick Reference: Signs You're Hitting a Limit

| Symptom | Likely bottleneck | First action |
|---------|-------------------|--------------|
| p95 latency spikes past 1s | DB connection contention | Add PgBouncer or reduce concurrency |
| Error rate > 0% (5xx) | Workers exhausted | Increase gunicorn workers or add servers |
| CPU pegged at 100% | Compute bound | Add workers or horizontal scale |
| Disk I/O wait high | Storage bottleneck | Move DB to SSD or dedicated server |
| `FATAL: remaining connection slots reserved` | `max_connections` hit | Add PgBouncer |

---

## Load Test Commands for Capacity Exploration

```bash
# Baseline: 50 VUs, 60s
uv run locust -f loadtests/locustfile.py \
  --host http://127.0.0.1:5000 \
  --users 50 --spawn-rate 50 --run-time 60s --headless

# Step up: 100 VUs
uv run locust -f loadtests/locustfile.py \
  --host http://127.0.0.1:5000 \
  --users 100 --spawn-rate 25 --run-time 60s --headless

# Find breaking point: 200 VUs
uv run locust -f loadtests/locustfile.py \
  --host http://127.0.0.1:5000 \
  --users 200 --spawn-rate 25 --run-time 60s --headless
```

Record each run in `loadtests/BASELINE.md` using the blank template provided.
