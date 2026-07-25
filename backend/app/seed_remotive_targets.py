"""Seed a single virtual target for the Remotive connector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal
from app.models import Connector, SourceTarget

TARGETS = [
    ("Remotive", "remotive", "https://remotive.com/api/remote-jobs", {}),
]

def run():
    db = SessionLocal()
    connector = db.query(Connector).filter(Connector.name == "remotive").first()
    if not connector:
        print("Connector 'remotive' not found — run seed_connectors.py first"); db.close(); return

    added = 0
    for company_name, company_key, base_url, config in TARGETS:
        exists = db.query(SourceTarget).filter(
            SourceTarget.connector_id == connector.id,
            SourceTarget.company_key == company_key,
        ).first()
        if not exists:
            db.add(SourceTarget(
                connector_id=connector.id,
                company_name=company_name,
                company_key=company_key,
                base_url=base_url,
                config_json=config,
                enabled=True,
                priority=10,
            ))
            added += 1
    db.commit()
    db.close()
    print(f"Remotive targets: {added} added")

if __name__ == "__main__":
    run()
