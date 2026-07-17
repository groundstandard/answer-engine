import json
import logging
from uuid import UUID
from typing import Optional, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.query_repo import QueryRepository

logger = logging.getLogger(__name__)
router = APIRouter()


class SourceUsage(BaseModel):
    source_name: str
    citation_count: int


class QueryLogItem(BaseModel):
    id: UUID
    query_text: str
    final_decision: Optional[str] = None
    policy_profile: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: str


class QueryLogPage(BaseModel):
    items: List[QueryLogItem]
    total: int
    limit: int
    offset: int


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


@router.get("/metrics/queries", response_model=QueryLogPage)
async def list_queries(
    tenant_id: UUID = Query(..., description="Tenant to list query logs for"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Paginated list of logged queries for a tenant (newest first)."""
    try:
        async with AsyncSessionLocal() as session:
            repo = QueryRepository(session)
            rows = await repo.list_for_tenant(tenant_id, limit, offset)
            total = await repo.count_for_tenant(tenant_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Query store unavailable: {e}")
    return QueryLogPage(
        items=[
            QueryLogItem(
                id=r["id"], query_text=r["query_text"], final_decision=r["final_decision"],
                policy_profile=r["policy_profile"], latency_ms=r["latency_ms"],
                created_at=str(r["created_at"]),
            )
            for r in rows
        ],
        total=total, limit=limit, offset=offset,
    )


class QueryGroup(BaseModel):
    query_text: str
    runs: int
    policy_profile: Optional[str] = None
    last_at: str
    run_list: List[dict]


class QueryGroupPage(BaseModel):
    items: List[QueryGroup]
    total: int
    limit: int
    offset: int


@router.get("/metrics/queries/grouped", response_model=QueryGroupPage)
async def list_queries_grouped(
    tenant_id: UUID = Query(..., description="Tenant to list grouped query logs for"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """One row per distinct question; every run collapsed into run_list (newest first)."""
    try:
        async with AsyncSessionLocal() as session:
            repo = QueryRepository(session)
            rows = await repo.list_grouped_for_tenant(tenant_id, limit, offset)
            total = await repo.count_distinct_for_tenant(tenant_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Query store unavailable: {e}")
    items = []
    for r in rows:
        rl = r["run_list"]
        if isinstance(rl, str):
            rl = json.loads(rl)
        items.append(QueryGroup(
            query_text=r["query_text"], runs=r["runs"],
            policy_profile=r["policy_profile"], last_at=str(r["last_at"]), run_list=rl,
        ))
    return QueryGroupPage(items=items, total=total, limit=limit, offset=offset)


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
