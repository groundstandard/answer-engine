import logging
from functools import lru_cache
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend.api.schemas.documents import DocumentIndexRequest, DocumentIndexResponse
from backend.services.indexing.indexer import DocumentIndexingService

logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_indexer() -> DocumentIndexingService:
    """Single shared indexing service (builds chunker/embedder/writer once)."""
    return DocumentIndexingService()


@router.post("/documents/index", response_model=DocumentIndexResponse, status_code=202)
async def index_document(request: DocumentIndexRequest):
    """
    Ingest a document into the evidence store for a tenant.
    Phase 1 accepts inline text content (PRD Section 12: text + PDF ingestion).
    """
    if not request.content or not request.content.strip():
        # PRD 3.1: never silent — reject clearly instead of indexing nothing.
        raise HTTPException(
            status_code=400,
            detail="Inline 'content' is required. URL fetching is not yet supported.",
        )

    document_id = uuid4()
    metadata = {**request.metadata}
    if request.title:
        metadata.setdefault("title", request.title)
    metadata.setdefault("document_id", str(document_id))

    try:
        result = await get_indexer().index_document(
            content=request.content,
            source_id=request.source_id,
            tenant_id=request.tenant_id,
            mime_type=request.content_type,
            metadata=metadata,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Indexing failure for source %s", request.source_id)
        raise HTTPException(status_code=500, detail=f"Indexing error: {e}")

    return DocumentIndexResponse(
        document_id=document_id,
        indexing_status=result.get("status", "indexed"),
        estimated_chunks=result.get("chunks"),
    )
