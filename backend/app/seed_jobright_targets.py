"""Seed a single virtual target for the JobRight connector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal
from app.models import Connector, SourceTarget

def run():
    db = SessionLocal()
    connector = db.query(Connector).filter(Connector.name == "jobright").first()
    if not connector:
        print("Connector 'jobright' not found — run seed_connectors.py first"); db.close(); return
    exists = db.query(SourceTarget).filter(
        SourceTarget.connector_id == connector.id, SourceTarget.company_key == "jobright"
    ).first()
    if not exists:
        db.add(SourceTarget(
            connector_id=connector.id, company_name="JobRight",
            company_key="jobright", base_url="https://jobright.ai",
            config_json={}, enabled=True, priority=10,
        ))
        db.commit()
        print("JobRight target: 1 added")
    else:
        print("JobRight target: already exists")
    db.close()

if __name__ == "__main__":
    run()
