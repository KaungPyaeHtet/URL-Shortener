from dotenv import load_dotenv
from flask import Flask, jsonify

from app.database import db, init_db
from app.routes import register_routes


def create_app():
    load_dotenv()

    app = Flask(__name__)

    init_db(app)

    from app import models  # noqa: F401 - registers models with Peewee

    register_routes(app)

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(error="not_found"), 404

    @app.route("/")
    def index():
        return jsonify(
            service="mlh-pe-hackathon",
            seed="PE/*.csv — load with: uv run python scripts/load_pe_seed.py",
            endpoints={
                "health": "/health",
                "users": "/api/users",
                "user": "/api/users/<id>",
                "urls": "/api/urls",
                "url": "/api/urls/<id>",
                "events": "/api/events",
                "redirect": "/s/<short_code>",
            },
        )

    @app.route("/health")
    def health():
        try:
            db.execute_sql("SELECT 1")
        except Exception:
            return jsonify(status="error", detail="database unreachable"), 503
        return jsonify(status="ok")

    return app
