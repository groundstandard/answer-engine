import json
import logging
from uuid import UUID
from typing import Optional, List

from sqlalchemy import text

from backend.models.evidence import EvidenceItem
from backend.database.connection import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _row_to_item(r) -> EvidenceItem:
    meta = r.metadata
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, ValueError):
            meta = {}
    tier = r.trust_tier if r.trust_tier is not None else 3
    return EvidenceItem(
        evidence_id=r.id,
        source_id=r.source_id,
        content=r.content,
        source_name=r.source_name,
        trust_score=tier / 5.0,
        freshness_score=1.0,
        trust_tier=tier,
        source_url=r.source_url,
        chunk_index=r.chunk_index or 0,
        relevance_score=float(r.score or 0.0),
        metadata=meta or {},
    )


class VectorSearchEngine:
    """Semantic similarity search via pgvector. Degrades to empty if embeddings unavailable."""

    def __init__(self):
        from backend.services.indexing.embedder import Embedder
        self.embedder = Embedder()

    async def search(
        self,
        query: str,
        rewritten_queries: List[str],
        tenant_id: UUID,
        source_scope: Optional[List[UUID]] = None,
        top_k: int = 20,
    ) -> List[EvidenceItem]:
        # If embeddings are unavailable (e.g. webhook not yet configured), skip
        # vector search entirely — BM25 keyword search still runs. No silent
        # wrong answers, just a narrower retrieval mode.
        try:
            qvec = await self.embedder.embed_query(query)
        except Exception as e:  # noqa: BLE001
            logger.warning("Vector search skipped — embeddings unavailable: %s", e)
            return []

        qvec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"
        sql = """
            SELECT e.id, e.source_id, e.content, e.chunk_index, e.metadata,
                   s.name AS source_name, s.url AS source_url, s.trust_tier,
                   1 - (e.embedding <=> CAST(:qvec AS vector)) AS score
            FROM evidence_items e
            JOIN sources s ON s.id = e.source_id
            WHERE e.tenant_id = :tenant_id
              AND s.is_active = TRUE
              AND e.embedding IS NOT NULL
        """
        params = {"qvec": qvec_literal, "tenant_id": str(tenant_id), "top_k": top_k}
        if source_scope:
            sql += " AND e.source_id::text = ANY(:scope)"
            params["scope"] = [str(s) for s in source_scope]
        sql += " ORDER BY e.embedding <=> CAST(:qvec AS vector) LIMIT :top_k"

        async with AsyncSessionLocal() as session:
            rows = (await session.execute(text(sql), params)).fetchall()
        return [_row_to_item(r) for r in rows]
