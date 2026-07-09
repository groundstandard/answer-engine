from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class TenantRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_policy_profile(self, tenant_id: UUID) -> Optional[str]:
        """Return the tenant's configured policy_profile, or None if unknown."""
        result = await self.db.execute(
            text("SELECT policy_profile FROM tenants WHERE id = :id"),
            {"id": str(tenant_id)},
        )
        row = result.fetchone()
        return row[0] if row else None
