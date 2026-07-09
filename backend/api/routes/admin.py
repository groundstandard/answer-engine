import logging
from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.review_repo import ReviewRepository

logger = logging.getLogger(__name__)
router = APIRouter()

_VALID_RESOLUTIONS = ("resolved", "dismissed")


class ReviewItem(BaseModel):
    id: UUID
    tenant_id: UUID
    query_text: str
    reason: Optional[str] = None
    status: str
    resolution_note: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


class ResolveRequest(BaseModel):
    status: str  # "resolved" | "dismissed"
    note: Optional[str] = None


@router.get("/admin/reviews", response_model=List[ReviewItem])
async def list_reviews(
    tenant_id: Optional[UUID] = Query(None),
    status: str = Query("pending"),
):
    """List human-review-queue items (default: pending)."""
    try:
        async with AsyncSessionLocal() as session:
            rows = await ReviewRepository(session).list_reviews(tenant_id, status)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Review store unavailable: {e}")
    return [
        ReviewItem(
            id=r["id"], tenant_id=r["tenant_id"], query_text=r["query_text"],
            reason=r["reason"], status=r["status"], resolution_note=r["resolution_note"],
            created_at=str(r["created_at"]),
            resolved_at=str(r["resolved_at"]) if r["resolved_at"] else None,
        )
        for r in rows
    ]


@router.post("/admin/reviews/{review_id}/resolve")
async def resolve_review(review_id: UUID, body: ResolveRequest):
    """Resolve or dismiss a queued review item."""
    if body.status not in _VALID_RESOLUTIONS:
        raise HTTPException(status_code=400, detail=f"status must be one of {_VALID_RESOLUTIONS}")
    try:
        async with AsyncSessionLocal() as session:
            ok = await ReviewRepository(session).resolve(review_id, body.status, body.note)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Review store unavailable: {e}")
    if not ok:
        raise HTTPException(status_code=404, detail="Pending review not found")
    return {"id": str(review_id), "status": body.status}
