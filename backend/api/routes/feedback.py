import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from backend.api.schemas.evaluations import FeedbackRequest, FeedbackResponse
from backend.database.connection import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(request: FeedbackRequest):
    """Submit user feedback on a query response."""
    if not 1 <= request.rating <= 5:
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")

    feedback_id = uuid4()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO feedback (id, query_log_id, rating, comment, created_at)
                    VALUES (:id, :query_log_id, :rating, :comment, NOW())
                """),
                {
                    "id": str(feedback_id),
                    "query_log_id": str(request.query_id),
                    "rating": request.rating,
                    "comment": request.comment,
                },
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        # A missing query_log (FK violation) or DB down — surface, don't swallow.
        logger.exception("Feedback insert failed")
        raise HTTPException(status_code=400, detail=f"Could not record feedback: {e}")

    return FeedbackResponse(feedback_id=feedback_id, status="recorded")
