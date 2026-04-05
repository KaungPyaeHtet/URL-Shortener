# Runbooks

Step-by-step guides for handling specific operational situations.

---

## Runbook 1: Service is Down (5xx errors or no response)

**Alert trigger:** Health check `GET /health` returns non-200 or times out.

**Steps:**

1. **Check if the process is running**
   ```bash
   sudo systemctl status hackathon   # systemd
   # or
   ps aux | grep gunicorn
   ```

2. **If not running, restart it**
   ```bash
   sudo systemctl restart hackathon
   curl http://localhost:5000/health
   ```

3. **If it crashes on startup, check logs**
   ```bash
   sudo journalctl -u hackathon -n 50 --no-pager
   ```
   - `could not connect to server` → go to Runbook 2 (DB down)
   - `ImportError` → virtualenv or code issue; check the deploy
   - `Address already in use` → `lsof -i :5000`, kill the orphan process, restart

4. **If the process is running but returning 5xx**, check app logs for a traceback and address the specific error.

---

## Runbook 2: Database is Unreachable

**Alert trigger:** `peewee.OperationalError` in logs, or health check failing after app starts.

**Steps:**

1. **Check PostgreSQL status**
   ```bash
   sudo systemctl status postgresql
   ```

2. **If stopped, start it**
   ```bash
   sudo systemctl start postgresql
   sudo systemctl restart hackathon   # restart app to reconnect
   ```

3. **Verify connectivity**
   ```bash
   psql -U postgres -d hackathon_db -c "SELECT 1;"
   ```

4. **If connection refused, check what port Postgres is listening on**
   ```bash
   sudo -u postgres psql -c "SHOW port;"
   # Compare to DATABASE_PORT in .env
   ```

5. **Check disk space** (full disk causes Postgres to stop accepting writes)
   ```bash
   df -h
   ```

---

## Runbook 3: High Latency (p95 > 1000ms)

**Alert trigger:** Load test p95 exceeds 1s, or users report slow responses.

**Steps:**

1. **Check if the slow endpoint is the redirect** (`/s/<short_code>`)
   - The `short_code` column has a unique index. If missing, queries will full-scan.
   ```bash
   psql -U postgres -d hackathon_db \
     -c "\d urls"   # look for index on short_code
   ```
   - If missing: `CREATE UNIQUE INDEX ON urls (short_code);`

2. **Check active DB connections**
   ```bash
   psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
   ```
   If near `max_connections` (default 100), connections are queuing.

3. **Check number of gunicorn workers**
   ```bash
   ps aux | grep gunicorn | grep worker | wc -l
   ```
   Rule of thumb: `2 × CPU_cores + 1`. Adjust `--workers` in your systemd service and restart.

4. **Run a targeted load test to isolate the slow endpoint**
   ```bash
   uv run locust -f loadtests/locustfile.py \
     --host http://127.0.0.1:5000 \
     --users 10 --spawn-rate 10 --run-time 30s --headless
   ```

---

## Runbook 4: Database Table is Empty / Missing Data

**Alert trigger:** API returns empty arrays for all requests; seed data not present.

**Steps:**

1. **Verify the tables exist and have rows**
   ```bash
   psql -U postgres -d hackathon_db <<'SQL'
   SELECT 'users' AS tbl, COUNT(*) FROM users
   UNION ALL
   SELECT 'urls', COUNT(*) FROM urls
   UNION ALL
   SELECT 'events', COUNT(*) FROM events;
   SQL
   ```

2. **If tables are empty or missing, reload seed data**
   ```bash
   # Ensure PE/users.csv, PE/urls.csv, PE/events.csv exist
   ls PE/

   # Load (--reset drops and recreates tables first)
   uv run python scripts/load_pe_seed.py --reset
   ```

3. **Verify after loading**
   ```bash
   psql -U postgres -d hackathon_db \
     -c "SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM urls; SELECT COUNT(*) FROM events;"
   ```

---

## Runbook 5: CI is Failing

**Alert trigger:** GitHub Actions CI badge is red; push blocked from merging.

**Steps:**

1. **Open the failing workflow** on GitHub → Actions tab → click the failed run.

2. **Common failures and fixes:**

   | Error | Fix |
   |-------|-----|
   | `psycopg2.OperationalError` | PostgreSQL service container not healthy — check the `--health-cmd` options in `ci.yml` |
   | `ModuleNotFoundError` | New dependency added to `pyproject.toml` but `uv.lock` not committed |
   | `AssertionError` in tests | A test is failing — read the pytest output for the specific assertion |
   | `uv sync` fails | Python version mismatch — check `.python-version` matches `requires-python` in `pyproject.toml` |

3. **Reproduce locally**
   ```bash
   uv sync --group dev
   uv run pytest -v
   ```
