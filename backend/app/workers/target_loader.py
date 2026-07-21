from sqlalchemy.orm import Session

from app.models import Connector, SourceTarget
from app.workers.connectors.base import SourceTargetDTO


def load_enabled_targets(
    db: Session,
    connector_names: list[str] | None = None,
    target_ids: list[str] | None = None,
) -> list[SourceTargetDTO]:
    q = db.query(SourceTarget).filter(SourceTarget.enabled.is_(True))
    if connector_names:
        q = q.join(Connector).filter(Connector.name.in_(connector_names))
    if target_ids:
        q = q.filter(SourceTarget.id.in_(target_ids))
    targets = q.order_by(SourceTarget.priority.asc()).all()
    return [
        SourceTargetDTO(
            id=t.id,
            connector_name=t.connector.name,
            company_name=t.company_name,
            base_url=t.base_url,
            company_key=t.company_key,
            target_slug=t.target_slug,
            config=t.config_json or {},
        )
        for t in targets
    ]
