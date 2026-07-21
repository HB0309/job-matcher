"""Seed a single virtual target for The Muse connector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import SessionLocal
from app.models import Connector, SourceTarget

def run():
    db = SessionLocal()
    connector = db.query(Connector).filter(Connector.name == "themuse").first()
    if not connector:
        print("Connector 'themuse' not found — run seed_connectors.py first"); db.close(); return

    exists = db.query(SourceTarget).filter(
        SourceTarget.connector_id == connector.id,
        SourceTarget.company_key == "themuse",
    ).first()
    if not exists:
        db.add(SourceTarget(
            connector_id=connector.id,
            company_name="The Muse",
            company_key="themuse",
            base_url="https://www.themuse.com/api/public/jobs",
            config_json={},
            enabled=True,
            priority=10,
        ))
        db.commit()
        print("The Muse target: 1 added")
    else:
        print("The Muse target: already exists")
    db.close()

if __name__ == "__main__":
    run()
