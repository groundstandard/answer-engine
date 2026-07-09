from uuid import UUID
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class DocumentsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_source(self, source_id: UUID, tenant_id: UUID, name: str, url: Optional[str], trust_tier: int) -> None:
        await self.db.execute(
            text("""
                INSERT INTO sources (id, tenant_id, name, url, trust_tier, created_at)
                VALUES (:id, :tenant_id, :name, :url, :trust_tier, NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": str(source_id), "tenant_id": str(tenant_id), "name": name, "url": url, "trust_tier": trust_tier},
        )
        await self.db.commit()

    async def list_sources(self, tenant_id: UUID) -> List[dict]:
        result = await self.db.execute(
            text("SELECT * FROM sources WHERE tenant_id = :tenant_id ORDER BY created_at DESC"),
            {"tenant_id": str(tenant_id)},
        )
        return [dict(row._mapping) for row in result.fetchall()]
