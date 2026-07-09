import json
from uuid import UUID
from typing import Optional, List

from sqlalchemy import text

from backend.models.evidence import EvidenceItem
from backend.database.connection import AsyncSessionLocal


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
        relevance_score=float(r.rank or 0.0),
        metadata=meta or {},
    )


class BM25SearchEngine:
    """Keyword search over evidence_items using PostgreSQL full-text ranking."""

    async def search(
        self,
        query: str,
        tenant_id: UUID,
        source_scope: Optional[List[UUID]] = None,
        top_k: int = 20,
    ) -> List[EvidenceItem]:
        sql = """
            SELECT e.id, e.source_id, e.content, e.chunk_index, e.metadata,
                   s.name AS source_name, s.url AS source_url, s.trust_tier,
                   ts_rank(to_tsvector('english', e.content),
                           plainto_tsquery('english', :q)) AS rank
            FROM evidence_items e
            JOIN sources s ON s.id = e.source_id
            WHERE e.tenant_id = :tenant_id
              AND s.is_active = TRUE
              AND to_tsvector('english', e.content) @@ plainto_tsquery('english', :q)
        """
        params = {"q": query, "tenant_id": str(tenant_id), "top_k": top_k}
        if source_scope:
            sql += " AND e.source_id::text = ANY(:scope)"
            params["scope"] = [str(s) for s in source_scope]
        sql += " ORDER BY rank DESC LIMIT :top_k"

        async with AsyncSessionLocal() as session:
            rows = (await session.execute(text(sql), params)).fetchall()
        return [_row_to_item(r) for r in rows]
