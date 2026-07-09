import logging
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException

from backend.api.schemas.query import QueryRequest, QueryResponse, QueryTraceResponse
from backend.orchestration.pipeline import PipelineController
from backend.orchestration.model_client import MODEL_OVERRIDES
from backend.config.policy_loader import load_policy_config, resolve_profile_for_domain
from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.query_repo import QueryRepository
from backend.database.repositories.tenant_repo import TenantRepository
from backend.database.repositories.review_repo import ReviewRepository

logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_pipeline() -> PipelineController:
    """Single shared pipeline instance (builds model client + services once)."""
    return PipelineController()


async def _resolve_policy(request: QueryRequest):
    """
    Pick the effective policy: the tenant's configured profile (from DB) vs the
    profile implied by the query domain — whichever is STRICTER wins, so a
    high-risk domain can never be answered under a lax tenant policy.
    """
    domain_profile = resolve_profile_for_domain(request.domain_hint)
    tenant_profile = "default"
    try:
        async with AsyncSessionLocal() as session:
            tp = await TenantRepository(session).get_policy_profile(request.tenant_id)
            if tp:
                tenant_profile = tp
    except Exception as e:  # noqa: BLE001 — tenant lookup is best-effort
        logger.warning("Tenant policy lookup skipped (DB unavailable): %s", e)

    cfg_tenant = load_policy_config(tenant_profile)
    cfg_domain = load_policy_config(domain_profile)
    if cfg_tenant.minimum_claim_support_ratio >= cfg_domain.minimum_claim_support_ratio:
        return tenant_profile, cfg_tenant
    return domain_profile, cfg_domain


async def _resolve_model_overrides(tenant_id) -> dict:
    """Best-effort load of the tenant's per-task model overrides."""
    try:
        async with AsyncSessionLocal() as session:
            return await TenantRepository(session).get_model_overrides(tenant_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Model-override lookup skipped (DB unavailable): %s", e)
        return {}


async def _log_query_trace(query_id, req: QueryRequest, response, profile: str) -> None:
    """
    Best-effort trace logging (PRD 2.1: synchronous pipeline, asynchronous logging).
    A DB failure must NEVER break the user-facing response.
    """
    try:
        async with AsyncSessionLocal() as session:
            repo = QueryRepository(session)
            trace = {
                "final_response": response.to_dict(),
                "policy_profile": profile,
                "user_id": str(req.user_id) if req.user_id else None,
            }
            await repo.save_query(
                query_id=query_id,
                tenant_id=req.tenant_id,
                query_text=req.query,
                final_decision=response.final_decision,
                user_id=req.user_id,
                policy_profile=profile,
                latency_ms=response.latency_ms,
                trace=trace,
            )
    except Exception as e:  # noqa: BLE001 — logging is best-effort by design
        logger.warning("Query trace logging skipped (DB unavailable): %s", e)


async def _enqueue_review(query_id, req: QueryRequest, response) -> None:
    """Best-effort: push an escalated query into the human review queue."""
    try:
        async with AsyncSessionLocal() as session:
            await ReviewRepository(session).enqueue(
                tenant_id=req.tenant_id,
                query_text=req.query,
                reason=response.refusal_reason or response.confidence_summary,
                query_log_id=query_id,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("Review enqueue skipped (DB unavailable): %s", e)


@router.post("/query", response_model=QueryResponse, status_code=200)
async def submit_query(request: QueryRequest):
    """
    Submit a query for evidence-gated processing.
    Returns VERIFIED, QUALIFIED, or REFUSED response with citations.
    """
    query_id = uuid4()
    profile, policy_config = await _resolve_policy(request)
    overrides = await _resolve_model_overrides(request.tenant_id)

    token = MODEL_OVERRIDES.set(overrides)
    try:
        final = await get_pipeline().run_pipeline(
            query=request.query,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            policy_config=policy_config,
            source_scope=request.allowed_sources,
            domain_hint=request.domain_hint,
        )
    except Exception as e:  # noqa: BLE001
        # PRD 3.1: never a silent fallback — surface a structured 5xx.
        logger.exception("Pipeline failure for query %s", query_id)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")
    finally:
        MODEL_OVERRIDES.reset(token)

    # Use one consistent id for the response and its trace record.
    final.query_id = query_id
    await _log_query_trace(query_id, request, final, profile)

    # Escalated answers go to the human review queue (best-effort).
    if final.final_decision == "ESCALATED":
        await _enqueue_review(query_id, request, final)

    return QueryResponse(**final.to_dict())


@router.get("/query/{query_id}", response_model=QueryTraceResponse)
async def get_query_trace(query_id: UUID):
    """Retrieve the full pipeline trace for a completed query."""
    try:
        async with AsyncSessionLocal() as session:
            repo = QueryRepository(session)
            row = await repo.get_query(query_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Trace store unavailable: {e}")

    if not row:
        raise HTTPException(status_code=404, detail="Query not found")

    trace = row.get("trace") or {}
    return QueryTraceResponse(
        query_id=query_id,
        query_text=row.get("query_text", ""),
        created_at=str(row.get("created_at", "")),
        classification=trace.get("classification", {}),
        evidence_summary=trace.get("evidence_summary", {}),
        claims=trace.get("claims", []),
        policy_decision=trace.get("policy_decision", {}),
        final_response=trace.get("final_response", {}),
    )
