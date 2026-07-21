"""Seed a single virtual target for the Adzuna connector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal
from app.models import Connector, SourceTarget

def run():
    db = SessionLocal()
    connector = db.query(Connector).filter(Connector.name == "adzuna").first()
    if not connector:
        print("Connector 'adzuna' not found — run seed_connectors.py first"); db.close(); return

    exists = db.query(SourceTarget).filter(
        SourceTarget.connector_id == connector.id,
        SourceTarget.company_key == "adzuna",
    ).first()
    if not exists:
        db.add(SourceTarget(
            connector_id=connector.id,
            company_name="Adzuna (United States)",
            company_key="adzuna",
            base_url="https://api.adzuna.com/v1/api/jobs/us/search",
            config_json={"location": "United States"},
            enabled=True,
            priority=10,
        ))
        db.commit()
        print("Adzuna target: 1 added")
    else:
        print("Adzuna target: already exists")
    db.close()

if __name__ == "__main__":
    run()
