"""Load PE/*.csv into Postgres. Run from repo root: uv run python scripts/load_pe_seed.py"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv
from peewee import chunked

ROOT = Path(__file__).resolve().parents[1]
PE_DIR = ROOT / "PE"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from app.csv_parse import parse_bool, parse_dt  # noqa: E402
from app.database import connect_db_cli, db  # noqa: E402
from app.models import Event, Url, User  # noqa: E402


def load_users(path: Path) -> None:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    batch = [
        {
            "id": int(r["id"]),
            "username": r["username"],
            "email": r["email"],
            "created_at": parse_dt(r["created_at"]),
        }
        for r in rows
    ]
    with db.atomic():
        for chunk in chunked(batch, 200):
            User.insert_many(chunk).execute()


def load_urls(path: Path) -> None:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    batch = [
        {
            "id": int(r["id"]),
            "user_id": int(r["user_id"]),
            "short_code": r["short_code"],
            "original_url": r["original_url"],
            "title": r["title"],
            "is_active": parse_bool(r["is_active"]),
            "created_at": parse_dt(r["created_at"]),
            "updated_at": parse_dt(r["updated_at"]),
        }
        for r in rows
    ]
    with db.atomic():
        for chunk in chunked(batch, 200):
            Url.insert_many(chunk).execute()


def load_events(path: Path) -> None:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    batch = [
        {
            "id": int(r["id"]),
            "url_id": int(r["url_id"]),
            "user_id": int(r["user_id"]),
            "event_type": r["event_type"],
            "timestamp": parse_dt(r["timestamp"]),
            "details": r["details"],
        }
        for r in rows
    ]
    with db.atomic():
        for chunk in chunked(batch, 200):
            Event.insert_many(chunk).execute()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load PE/*.csv into the hackathon database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop urls/events/users tables (CASCADE) then recreate before load.",
    )
    parser.add_argument(
        "--pe-dir",
        type=Path,
        default=PE_DIR,
        help=f"Directory with users.csv, urls.csv, events.csv (default: {PE_DIR})",
    )
    args = parser.parse_args()

    users_csv = args.pe_dir / "users.csv"
    urls_csv = args.pe_dir / "urls.csv"
    events_csv = args.pe_dir / "events.csv"
    for p in (users_csv, urls_csv, events_csv):
        if not p.is_file():
            raise SystemExit(f"Missing seed file: {p}")

    connect_db_cli()
    try:
        if args.reset:
            db.drop_tables([Event, Url, User], safe=True, cascade=True)
        db.create_tables([User, Url, Event], safe=True)

        load_users(users_csv)
        load_urls(urls_csv)
        load_events(events_csv)

        print(
            f"Loaded {User.select().count()} users, "
            f"{Url.select().count()} urls, "
            f"{Event.select().count()} events."
        )
    finally:
        if not db.is_closed():
            db.close()


if __name__ == "__main__":
    main()
