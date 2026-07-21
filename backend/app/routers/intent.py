from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.schemas import (
    IntentAssessmentResponse,
    IntentAssessRequest,
    IntentBatchRequest,
)
from app.workers import intent_engine

router = APIRouter(prefix="/intent", tags=["intent"], dependencies=[Depends(get_current_user)])


@router.post("/assess", response_model=IntentAssessmentResponse)
def assess(body: IntentAssessRequest, db: Session = Depends(get_db)):
    return intent_engine.assess(
        db,
        surface=body.surface,
        profile_id=body.profile_id,
        saved_job_id=body.saved_job_id,
    )


@router.post("/assess-batch", response_model=list[IntentAssessmentResponse])
def assess_batch(body: IntentBatchRequest, db: Session = Depends(get_db)):
    return intent_engine.assess_batch(
        db,
        surface=body.surface,
        profile_id=body.profile_id,
        saved_job_ids=body.saved_job_ids,
    )
