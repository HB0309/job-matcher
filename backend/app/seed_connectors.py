"""
Seed script — inserts aggregator connectors into the database.

Run from the backend/ directory after `alembic upgrade head`:
    python -m app.seed_connectors
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal
from app.models import Connector

CONNECTORS = [
    {
        "name": "jobright",
        "display_name": "JobRight",
        "enabled": True,
        "auth_mode": "public",
        "notes": "JobRight public Next.js API — no auth, search-based.",
    },
    {
        "name": "hiringcafe",
        "display_name": "Hiring Café",
        "enabled": True,
        "auth_mode": "public",
        "notes": "hiring.cafe public Next.js SSR — no auth, search-based.",
    },
    {
        "name": "themuse",
        "display_name": "The Muse",
        "enabled": True,
        "auth_mode": "public",
        "notes": "The Muse public API — no auth. Filters by Software Engineering category + level.",
    },
    {
        "name": "adzuna",
        "display_name": "Adzuna",
        "enabled": True,
        "auth_mode": "api_key",
        "notes": "Adzuna aggregator API — free key at developer.adzuna.com. Set ADZUNA_APP_ID + ADZUNA_APP_KEY in .env.",
    },
    {
        "name": "indeed",
        "display_name": "Indeed",
        "enabled": True,
        "auth_mode": "public",
        "notes": "Public RSS feed — no auth. Search-based across all companies.",
    },
    {
        "name": "dice",
        "display_name": "Dice",
        "enabled": True,
        "auth_mode": "public",
        "notes": "Dice public job search API — tech-focused, no auth.",
    },
    {
        "name": "remoteok",
        "display_name": "RemoteOK",
        "enabled": True,
        "auth_mode": "public",
        "notes": "RemoteOK public JSON API — remote-only jobs, no auth.",
    },
    {
        "name": "remotive",
        "display_name": "Remotive",
        "enabled": True,
        "auth_mode": "public",
        "notes": "Remotive public REST API — remote tech jobs, no auth. HTML-stripped descriptions.",
    },
    {
        "name": "linkedin",
        "display_name": "LinkedIn",
        "enabled": True,
        "auth_mode": "public",
        "notes": "Guest search API — no login required; search-based across all companies, not per-company.",
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for data in CONNECTORS:
            existing = db.query(Connector).filter(Connector.name == data["name"]).first()
            if existing:
                skipped += 1
                print(f"  skip  {data['name']} (already exists)")
            else:
                db.add(Connector(**data))
                inserted += 1
                print(f"  add   {data['name']}")
        db.commit()
        print(f"\nDone — {inserted} inserted, {skipped} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
