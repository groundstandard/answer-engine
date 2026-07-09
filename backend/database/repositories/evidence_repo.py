from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class EvidenceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_evidence_item(self, evidence_id: UUID, source_id: UUID, tenant_id: UUID, content: str, chunk_index: int) -> None:
        await self.db.execute(
            text("""
                INSERT INTO evidence_items (id, source_id, tenant_id, content, chunk_index, created_at)
                VALUES (:id, :source_id, :tenant_id, :content, :chunk_index, NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(evidence_id),
                "source_id": str(source_id),
                "tenant_id": str(tenant_id),
                "content": content,
                "chunk_index": chunk_index,
            },
        )
        await self.db.commit()
