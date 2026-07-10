from uuid import UUID
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class SourcesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        tenant_id: UUID,
        name: str,
        url: Optional[str],
        description: Optional[str],
        trust_tier: int,
    ) -> dict:
        result = await self.db.execute(
            text("""
                INSERT INTO sources (tenant_id, name, url, description, trust_tier, is_active)
                VALUES (:tenant_id, :name, :url, :description, :trust_tier, TRUE)
                RETURNING id, name, url, trust_tier, is_active, created_at
            """),
            {
                "tenant_id": str(tenant_id),
                "name": name,
                "url": url,
                "description": description,
                "trust_tier": trust_tier,
            },
        )
        row = result.fetchone()
        await self.db.commit()
        return dict(row._mapping)

    async def delete(self, source_id: UUID, tenant_id: UUID) -> bool:
        """Delete a source (its evidence_items + checksums cascade)."""
        result = await self.db.execute(
            text("DELETE FROM sources WHERE id = :id AND tenant_id = :tenant_id"),
            {"id": str(source_id), "tenant_id": str(tenant_id)},
        )
        await self.db.commit()
        return result.rowcount > 0

    async def list_for_tenant(self, tenant_id: UUID) -> List[dict]:
        result = await self.db.execute(
            text("""
                SELECT id, name, url, trust_tier, is_active, created_at
                FROM sources
                WHERE tenant_id = :tenant_id
                ORDER BY created_at DESC
            """),
            {"tenant_id": str(tenant_id)},
        )
        return [dict(r._mapping) for r in result.fetchall()]
