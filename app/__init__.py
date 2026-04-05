import logging
import os

import psutil
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from app.database import db, ensure_tables, init_db
from app.logging_config import LOG_FILE, setup_logging
from app.prom_metrics import init_prom_metrics
from app.routes import register_routes

log = logging.getLogger(__name__)


def create_app():
    load_dotenv()
    setup_logging()

    app = Flask(__name__)

    log.info("Starting mlh-pe-hackathon service")

    init_db(app)

    from app import models  # noqa: F401 - registers models with Peewee

    ensure_tables()

    register_routes(app)
    init_prom_metrics(app)

    # ── Request logging ────────────────────────────────────────────────────────

    @app.before_request
    def _log_request():
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "remote_addr": request.remote_addr,
            },
        )

    @app.after_request
    def _log_response(response):
        log.info(
            "response",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
            },
        )
        return response

    # ── Error handlers ─────────────────────────────────────────────────────────

    @app.errorhandler(404)
    def not_found(_e):
        log.warning("not_found", extra={"path": request.path})
        return jsonify(error="not_found"), 404

    @app.errorhandler(500)
    def internal_error(e):
        log.error("internal_server_error", extra={"error": str(e)}, exc_info=True)
        return jsonify(error="internal_server_error"), 500

    # ── Routes ─────────────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return jsonify(
            service="mlh-pe-hackathon",
            seed="PE/*.csv — load with: uv run python scripts/load_pe_seed.py",
            endpoints={
                "health": "GET /health",
                "metrics": "GET /metrics",
                "prom": "GET /prom",
                "logs": "GET /logs",
                "users": "GET /users",
                "users_bulk": "POST /users/bulk",
                "users_create": "POST /users",
                "user": "GET /users/<id>",
                "user_update": "PUT /users/<id>",
                "user_delete": "DELETE /users/<id>",
                "urls_list": "GET /urls",
                "urls_create": "POST /urls",
                "url": "GET /urls/<id>",
                "url_update": "PUT /urls/<id>",
                "url_delete": "DELETE /urls/<id>",
                "events": "GET /events",
                "redirect_s": "GET /s/<short_code>",
                "redirect_urls": "GET /urls/<short_code>/redirect",
            },
        )

    @app.route("/health")
    def health():
        try:
            db.execute_sql("SELECT 1")
        except Exception:
            log.error("health_check_failed", extra={"detail": "database unreachable"})
            return jsonify(status="error", detail="database unreachable"), 503
        return jsonify(status="ok")

    @app.route("/metrics")
    def metrics():
        mem = psutil.virtual_memory()
        cpu_times = psutil.cpu_times_percent(interval=None)
        return jsonify(
            cpu={
                "percent": psutil.cpu_percent(interval=0.1),
                "count_logical": psutil.cpu_count(logical=True),
                "count_physical": psutil.cpu_count(logical=False),
                "user_percent": cpu_times.user,
                "system_percent": cpu_times.system,
                "idle_percent": cpu_times.idle,
            },
            memory={
                "total_mb": round(mem.total / 1024 / 1024, 1),
                "available_mb": round(mem.available / 1024 / 1024, 1),
                "used_mb": round(mem.used / 1024 / 1024, 1),
                "percent": mem.percent,
            },
            process={
                "pid": os.getpid(),
                "rss_mb": round(
                    psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 2
                ),
            },
        )

    @app.route("/logs")
    def view_logs():
        """Return the last N lines of the JSON log file."""
        try:
            n = min(max(1, int(request.args.get("lines", 100))), 1000)
        except (TypeError, ValueError):
            n = 100

        try:
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
            tail = [line.rstrip() for line in lines[-n:]]
        except FileNotFoundError:
            tail = []

        return jsonify(log_file=LOG_FILE, lines_returned=len(tail), logs=tail)

    return app
