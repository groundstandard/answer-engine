import json
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

    async def get_model_overrides(self, tenant_id: UUID) -> dict:
        """Return the tenant's per-task model overrides ({} if none/unknown)."""
        result = await self.db.execute(
            text("SELECT model_overrides FROM tenants WHERE id = :id"),
            {"id": str(tenant_id)},
        )
        row = result.fetchone()
        if not row or row[0] is None:
            return {}
        val = row[0]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                return {}
        return val if isinstance(val, dict) else {}
