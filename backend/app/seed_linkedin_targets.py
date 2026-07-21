"""
Seed script — inserts one virtual LinkedIn source target.

LinkedIn is search-based: one target represents the entire LinkedIn job board.
Keywords are derived from the profile's preferred_titles at fetch time.

Run from the backend/ directory after `alembic upgrade head` and `python -m app.seed_connectors`:
    python -m app.seed_linkedin_targets
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal
from app.models import Connector, SourceTarget

# (company_name, company_key)
# One virtual entry — keywords come from the profile query at runtime.
TARGETS = [
    ("LinkedIn Job Search", "linkedin"),
]


def seed() -> None:
    db = SessionLocal()
    try:
        connector = db.query(Connector).filter(Connector.name == "linkedin").first()
        if not connector:
            print("ERROR: 'linkedin' connector not found. Run `python -m app.seed_connectors` first.")
            return

        inserted = 0
        skipped = 0
        for company_name, company_key in TARGETS:
            existing = (
                db.query(SourceTarget)
                .filter(
                    SourceTarget.connector_id == connector.id,
                    SourceTarget.company_key == company_key,
                )
                .first()
            )
            if existing:
                skipped += 1
                print(f"  skip  {company_name} (already exists)")
            else:
                db.add(
                    SourceTarget(
                        connector_id=connector.id,
                        company_name=company_name,
                        company_key=company_key,
                        base_url="https://www.linkedin.com",
                        enabled=True,
                    )
                )
                inserted += 1
                print(f"  add   {company_name}")
        db.commit()
        print(f"\nDone — {inserted} inserted, {skipped} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
