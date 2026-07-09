import logging
from uuid import UUID
from typing import List

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas.documents import SourceCreate, SourceResponse
from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.sources_repo import SourcesRepository

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_response(row: dict, source_type: str = "document") -> SourceResponse:
    return SourceResponse(
        source_id=row["id"],
        source_name=row["name"],
        source_type=source_type,
        trust_tier=row["trust_tier"],
        enabled=row["is_active"],
        last_indexed_at=None,
    )


@router.get("/sources", response_model=List[SourceResponse])
async def list_sources(tenant_id: UUID = Query(..., description="Tenant to list sources for")):
    """List all configured evidence sources for a tenant."""
    try:
        async with AsyncSessionLocal() as session:
            rows = await SourcesRepository(session).list_for_tenant(tenant_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Source store unavailable: {e}")
    return [_to_response(r) for r in rows]


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(request: SourceCreate):
    """Register a new evidence source for the tenant."""
    if not 1 <= request.trust_tier <= 5:
        raise HTTPException(status_code=400, detail="trust_tier must be between 1 and 5")
    try:
        async with AsyncSessionLocal() as session:
            row = await SourcesRepository(session).create(
                tenant_id=request.tenant_id,
                name=request.source_name,
                url=request.source_url,
                description=request.description,
                trust_tier=request.trust_tier,
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("Source creation failed")
        raise HTTPException(status_code=500, detail=f"Could not create source: {e}")
    return _to_response(row, source_type=request.source_type)
