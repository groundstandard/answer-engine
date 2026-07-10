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
    Accepts inline text ('content') or a base64 PDF ('pdf_base64') — PRD Section 12.
    """
    content = request.content
    if request.pdf_base64:
        try:
            from backend.services.indexing.pdf_extract import extract_text_from_pdf_base64
            content = extract_text_from_pdf_base64(request.pdf_base64)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")

    if not content or not content.strip():
        # PRD 3.1: never silent — reject clearly instead of indexing nothing.
        raise HTTPException(
            status_code=400,
            detail="Provide 'content' or a 'pdf_base64' with extractable text.",
        )

    document_id = uuid4()
    metadata = {**request.metadata}
    if request.title:
        metadata.setdefault("title", request.title)
    metadata.setdefault("document_id", str(document_id))

    try:
        result = await get_indexer().index_document(
            content=content,
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
