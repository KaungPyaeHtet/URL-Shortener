# Deploy Guide

## Local Development

```bash
uv sync --group dev
cp .env.example .env      # fill in your DB credentials
createdb hackathon_db
uv run python scripts/load_pe_seed.py
uv run run.py             # http://localhost:5000
```

---

## Production Deployment

### Option A — Bare Metal / VPS (e.g. Ubuntu 24.04)

**1. Install dependencies on the server**

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install PostgreSQL (if not already running)
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

**2. Create database and user**

```bash
sudo -u postgres psql <<'SQL'
CREATE USER hackathon WITH PASSWORD 'changeme';
CREATE DATABASE hackathon_db OWNER hackathon;
SQL
```

**3. Clone and configure**

```bash
git clone <repo-url> /opt/hackathon && cd /opt/hackathon
cp .env.example .env
# Edit .env — set DATABASE_PASSWORD, FLASK_DEBUG=false, etc.
uv sync
```

**4. Load seed data**

```bash
uv run python scripts/load_pe_seed.py
```

**5. Run with gunicorn (production WSGI)**

```bash
uv add gunicorn
uv run gunicorn "app:create_app()" \
  --workers 4 \
  --bind 0.0.0.0:5000 \
  --access-logfile - \
  --error-logfile -
```

**6. (Optional) systemd service**

```ini
# /etc/systemd/system/hackathon.service
[Unit]
Description=MLH PE Hackathon API
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/hackathon
EnvironmentFile=/opt/hackathon/.env
ExecStart=/opt/hackathon/.venv/bin/gunicorn "app:create_app()" \
          --workers 4 --bind 0.0.0.0:5000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now hackathon
```

---

### Option B — Docker

```dockerfile
# Dockerfile (add to repo root if needed)
FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install uv && uv sync --no-dev
EXPOSE 5000
CMD ["uv", "run", "gunicorn", "app:create_app()", "--bind", "0.0.0.0:5000", "--workers", "4"]
```

```bash
docker build -t hackathon-api .
docker run -p 5000:5000 --env-file .env hackathon-api
```

---

## Rollback Procedure

### Application rollback

```bash
# Find the last good commit
git log --oneline -10

# Revert to it
git checkout <good-commit-sha>
sudo systemctl restart hackathon   # or restart your container
```

### Database rollback

The seed script supports a full reset. **This wipes all data** — only use if re-seeding from CSV is acceptable:

```bash
uv run python scripts/load_pe_seed.py --reset
```

If you need point-in-time recovery, restore from your PostgreSQL backup:

```bash
# Restore from pg_dump backup
pg_restore -U postgres -d hackathon_db /backups/hackathon_db_<date>.dump
```

---

## CI/CD (GitHub Actions)

Every push triggers `.github/workflows/ci.yml`:
1. Spins up PostgreSQL 16 as a service container.
2. Installs dependencies with `uv sync --group dev`.
3. Runs `uv run pytest -v`.

Merges to `main` only after CI passes.

---

## Checklist Before Going Live

- [ ] `FLASK_DEBUG=false` in production `.env`
- [ ] `DATABASE_PASSWORD` is a strong, unique password
- [ ] PostgreSQL not exposed on a public port (bind to `127.0.0.1`)
- [ ] Gunicorn (not Flask dev server) serving requests
- [ ] Systemd service set to `Restart=always`
- [ ] Seed data loaded: `uv run python scripts/load_pe_seed.py`
- [ ] `/health` returns `{"status": "ok"}`
- [ ] Load test passing: error rate 0%
