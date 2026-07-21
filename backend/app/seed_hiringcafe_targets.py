"""Seed a single virtual target for the Hiring Café connector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal
from app.models import Connector, SourceTarget

def run():
    db = SessionLocal()
    connector = db.query(Connector).filter(Connector.name == "hiringcafe").first()
    if not connector:
        print("Connector 'hiringcafe' not found — run seed_connectors.py first"); db.close(); return
    exists = db.query(SourceTarget).filter(
        SourceTarget.connector_id == connector.id, SourceTarget.company_key == "hiringcafe"
    ).first()
    if not exists:
        db.add(SourceTarget(
            connector_id=connector.id, company_name="Hiring Café",
            company_key="hiringcafe", base_url="https://hiring.cafe",
            config_json={}, enabled=True, priority=10,
        ))
        db.commit()
        print("Hiring Café target: 1 added")
    else:
        print("Hiring Café target: already exists")
    db.close()

if __name__ == "__main__":
    run()
