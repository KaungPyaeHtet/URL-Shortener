import os

from peewee import DatabaseProxy, Model, PostgresqlDatabase

db = DatabaseProxy()


class BaseModel(Model):
    class Meta:
        database = db


def _postgres_from_env() -> PostgresqlDatabase:
    return PostgresqlDatabase(
        os.environ.get("DATABASE_NAME", "hackathon_db"),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5432)),
        user=os.environ.get("DATABASE_USER", "postgres"),
        password=os.environ.get("DATABASE_PASSWORD", "postgres"),
    )


def connect_db_cli():
    """Initialize and open DB for scripts (after load_dotenv())."""
    database = _postgres_from_env()
    db.initialize(database)
    if db.is_closed():
        db.connect(reuse_if_open=True)
    return db


def init_db(app):
    database = _postgres_from_env()
    db.initialize(database)

    @app.before_request
    def _db_connect():
        db.connect(reuse_if_open=True)

    @app.teardown_appcontext
    def _db_close(exc):
        if not db.is_closed():
            db.close()
