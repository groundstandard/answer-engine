import logging
from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.review_repo import ReviewRepository
from backend.database.repositories.audit_repo import AuditRepository

logger = logging.getLogger(__name__)
router = APIRouter()

_VALID_RESOLUTIONS = ("resolved", "dismissed")
_STALE_DAYS = 30


class AssignRequest(BaseModel):
    reviewer_id: UUID


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


@router.post("/admin/reviews/{review_id}/assign")
async def assign_review(review_id: UUID, body: AssignRequest):
    """Assign a queued review to a reviewer (moves it to 'in_review')."""
    try:
        async with AsyncSessionLocal() as session:
            ok = await ReviewRepository(session).assign(review_id, body.reviewer_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Review store unavailable: {e}")
    if not ok:
        raise HTTPException(status_code=404, detail="Assignable review not found")
    return {"id": str(review_id), "status": "in_review", "assigned_to": str(body.reviewer_id)}


@router.get("/admin/audit")
async def audit_log(tenant_id: Optional[UUID] = Query(None), limit: int = Query(100, le=500)):
    """Read the append-only audit log (immutable)."""
    try:
        async with AsyncSessionLocal() as session:
            rows = await AuditRepository(session).list_for_tenant(tenant_id, limit)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Audit store unavailable: {e}")
    return [
        {
            "id": str(r["id"]), "tenant_id": str(r["tenant_id"]) if r["tenant_id"] else None,
            "query_id": str(r["query_id"]) if r["query_id"] else None,
            "event_type": r["event_type"], "decision": r["decision"],
            "created_at": str(r["created_at"]),
        } for r in rows
    ]


@router.get("/admin/freshness")
async def freshness(tenant_id: UUID = Query(...)):
    """
    Source freshness report: newest evidence age per source, flagging stale ones.
    (Lightweight version of PRD real-time freshness monitoring.)
    """
    sql = """
        SELECT s.name AS source_name, COUNT(e.id) AS chunks,
               MAX(e.created_at) AS latest_indexed,
               EXTRACT(EPOCH FROM (NOW() - MAX(e.created_at))) / 86400 AS age_days
        FROM sources s
        LEFT JOIN evidence_items e ON e.source_id = s.id
        WHERE s.tenant_id = :tenant_id
        GROUP BY s.name
        ORDER BY age_days DESC NULLS FIRST
    """
    try:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(text(sql), {"tenant_id": str(tenant_id)})).fetchall()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Freshness store unavailable: {e}")
    out = []
    for r in rows:
        age = float(r.age_days) if r.age_days is not None else None
        out.append({
            "source_name": r.source_name, "chunks": int(r.chunks or 0),
            "latest_indexed": str(r.latest_indexed) if r.latest_indexed else None,
            "age_days": round(age, 2) if age is not None else None,
            "is_stale": (age is not None and age > _STALE_DAYS) or r.chunks == 0,
        })
    return out


@router.get("/admin/calibration")
async def calibration(tenant_id: UUID = Query(...)):
    """
    Feedback-driven calibration report: average user rating per decision, with a
    plain-language hint on whether thresholds look too strict or too lax.
    (Lightweight version of PRD active-learning loop.)
    """
    sql = """
        SELECT q.final_decision AS decision, COUNT(f.id) AS n, AVG(f.rating) AS avg_rating
        FROM query_logs q JOIN feedback f ON f.query_log_id = q.id
        WHERE q.tenant_id = :tenant_id
        GROUP BY q.final_decision
    """
    try:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(text(sql), {"tenant_id": str(tenant_id)})).fetchall()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Calibration store unavailable: {e}")

    by_decision = {r.decision: {"feedback_count": int(r.n), "avg_rating": round(float(r.avg_rating), 2)} for r in rows}
    hints = []
    v = by_decision.get("VERIFIED", {}).get("avg_rating")
    ref = by_decision.get("REFUSED", {}).get("avg_rating")
    if v is not None and v < 3.0:
        hints.append("Low ratings on VERIFIED answers — thresholds may be too lax; consider raising minimum_claim_support_ratio.")
    if ref is not None and ref < 3.0:
        hints.append("Low ratings on REFUSED answers — thresholds may be too strict; consider lowering minimum_evidence_count.")
    if not hints:
        hints.append("No strong calibration signal yet (need more feedback).")
    return {"by_decision": by_decision, "suggestions": hints}
