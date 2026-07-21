from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Connector, SourceTarget
from app.schemas import (
    ConnectorSummary,
    SourcesResponse,
    SourceTargetCreateRequest,
    SourceTargetCreateResponse,
    SourceTargetItem,
    SourceTargetsResponse,
)

router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=SourcesResponse)
def list_sources(db: Session = Depends(get_db)) -> SourcesResponse:
    connectors = db.query(Connector).order_by(Connector.name).all()
    return SourcesResponse(
        sources=[
            ConnectorSummary(name=c.name, display_name=c.display_name, enabled=c.enabled)
            for c in connectors
        ]
    )


@router.get("/source-targets", response_model=SourceTargetsResponse)
def list_source_targets(
    connector: str | None = Query(default=None),
    enabled_only: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> SourceTargetsResponse:
    q = db.query(SourceTarget)
    if enabled_only:
        q = q.filter(SourceTarget.enabled.is_(True))
    if connector:
        q = q.join(Connector).filter(Connector.name == connector)
    targets = q.order_by(SourceTarget.priority.asc(), SourceTarget.company_name.asc()).all()
    return SourceTargetsResponse(
        targets=[
            SourceTargetItem(
                id=t.id,
                connector=t.connector.name,
                company_name=t.company_name,
                base_url=t.base_url,
                enabled=t.enabled,
                priority=t.priority,
                last_success_at=t.last_success_at,
            )
            for t in targets
        ]
    )


@router.post("/source-targets", response_model=SourceTargetCreateResponse, status_code=201)
def create_source_target(
    request: SourceTargetCreateRequest, db: Session = Depends(get_db)
) -> SourceTargetCreateResponse:
    connector = db.query(Connector).filter(Connector.name == request.connector).first()
    if not connector:
        raise HTTPException(400, f"Unknown connector: {request.connector!r}")
    if not connector.enabled:
        raise HTTPException(400, f"Connector {request.connector!r} is disabled")

    target = SourceTarget(
        connector_id=connector.id,
        company_name=request.company_name,
        company_key=request.company_key,
        base_url=request.base_url,
        enabled=request.enabled,
        priority=request.priority,
        config_json=request.config,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return SourceTargetCreateResponse(
        id=target.id,
        connector=connector.name,
        company_name=target.company_name,
        enabled=target.enabled,
    )
