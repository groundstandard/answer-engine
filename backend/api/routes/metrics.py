import logging
from uuid import UUID
from typing import Optional, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from backend.database.connection import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()


class SourceUsage(BaseModel):
    source_name: str
    citation_count: int


class MetricsResponse(BaseModel):
    tenant_id: Optional[UUID] = None
    total_queries: int
    by_decision: Dict[str, int]
    verified_rate: float
    qualified_rate: float
    refusal_rate: float
    avg_latency_ms: float


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(tenant_id: Optional[UUID] = Query(None, description="Scope to one tenant; omit for all")):
    """
    Aggregate dashboard metrics from query_logs (PRD Phase 2):
    verified / qualified / refusal rates and average latency.
    """
    sql = """
        SELECT final_decision AS decision, COUNT(*) AS n, AVG(latency_ms) AS avg_latency
        FROM query_logs
        {where}
        GROUP BY final_decision
    """
    params = {}
    if tenant_id:
        sql = sql.format(where="WHERE tenant_id = :tenant_id")
        params["tenant_id"] = str(tenant_id)
    else:
        sql = sql.format(where="")

    try:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(text(sql), params)).fetchall()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Metrics store unavailable: {e}")

    by_decision: Dict[str, int] = {}
    total = 0
    weighted_latency = 0.0
    for r in rows:
        decision = (r.decision or "UNKNOWN").upper()
        n = int(r.n or 0)
        by_decision[decision] = by_decision.get(decision, 0) + n
        total += n
        if r.avg_latency is not None:
            weighted_latency += float(r.avg_latency) * n

    def rate(*decisions: str) -> float:
        if not total:
            return 0.0
        return round(sum(by_decision.get(d, 0) for d in decisions) / total, 4)

    return MetricsResponse(
        tenant_id=tenant_id,
        total_queries=total,
        by_decision=by_decision,
        verified_rate=rate("VERIFIED"),
        qualified_rate=rate("QUALIFIED"),
        refusal_rate=rate("REFUSED"),
        avg_latency_ms=round(weighted_latency / total, 1) if total else 0.0,
    )


@router.get("/metrics/sources", response_model=List[SourceUsage])
async def source_analytics(tenant_id: Optional[UUID] = Query(None)):
    """
    Which sources actually contribute to answers — counts citations per source
    across logged query traces (PRD Phase 3: per-source retrieval analytics).
    """
    where = "WHERE tenant_id = :tenant_id" if tenant_id else ""
    sql = f"""
        SELECT c->>'source_name' AS source_name, COUNT(*) AS citation_count
        FROM query_logs,
             LATERAL jsonb_array_elements(trace->'final_response'->'citations') AS c
        {where}
        GROUP BY c->>'source_name'
        ORDER BY citation_count DESC
        LIMIT 100
    """
    params = {"tenant_id": str(tenant_id)} if tenant_id else {}
    try:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(text(sql), params)).fetchall()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Analytics store unavailable: {e}")
    return [SourceUsage(source_name=r.source_name or "unknown", citation_count=int(r.citation_count)) for r in rows]
