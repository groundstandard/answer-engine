import json
from uuid import UUID, uuid4
from typing import List, Optional

from sqlalchemy import text

from backend.services.indexing.chunker import Chunk
from backend.database.connection import AsyncSessionLocal


def _to_vector_literal(embedding: Optional[List[float]]) -> Optional[str]:
    """pgvector accepts a text literal like '[0.1,0.2,...]'; None -> NULL."""
    if not embedding:
        return None
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


class VectorWriter:
    """Persists chunks into the evidence_items table (pgvector column nullable)."""

    async def write(
        self,
        chunks: List[Chunk],
        embeddings: List[Optional[List[float]]],
        source_id: UUID,
        tenant_id: UUID,
    ) -> None:
        if not chunks:
            return
        async with AsyncSessionLocal() as session:
            for i, chunk in enumerate(chunks):
                emb = embeddings[i] if i < len(embeddings) else None
                await session.execute(
                    text("""
                        INSERT INTO evidence_items
                            (id, source_id, tenant_id, content, chunk_index, embedding, metadata, created_at)
                        VALUES
                            (:id, :source_id, :tenant_id, :content, :chunk_index,
                             CAST(:embedding AS vector), CAST(:metadata AS jsonb), NOW())
                    """),
                    {
                        "id": str(uuid4()),
                        "source_id": str(source_id),
                        "tenant_id": str(tenant_id),
                        "content": chunk.text,
                        "chunk_index": chunk.chunk_index,
                        "embedding": _to_vector_literal(emb),
                        "metadata": json.dumps(chunk.metadata or {}),
                    },
                )
            await session.commit()
