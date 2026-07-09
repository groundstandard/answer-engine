import json
from uuid import UUID, uuid4
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class AuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def write(
        self,
        event_type: str,
        tenant_id: Optional[UUID] = None,
        query_id: Optional[UUID] = None,
        decision: Optional[str] = None,
        detail: Optional[dict] = None,
    ) -> UUID:
        audit_id = uuid4()
        await self.db.execute(
            text("""
                INSERT INTO audit_log (id, tenant_id, query_id, event_type, decision, detail)
                VALUES (:id, :tenant_id, :query_id, :event_type, :decision, CAST(:detail AS jsonb))
            """),
            {
                "id": str(audit_id),
                "tenant_id": str(tenant_id) if tenant_id else None,
                "query_id": str(query_id) if query_id else None,
                "event_type": event_type,
                "decision": decision,
                "detail": json.dumps(detail or {}),
            },
        )
        await self.db.commit()
        return audit_id

    async def list_for_tenant(self, tenant_id: Optional[UUID], limit: int = 100) -> List[dict]:
        sql = "SELECT id, tenant_id, query_id, event_type, decision, created_at FROM audit_log"
        params = {"limit": limit}
        if tenant_id:
            sql += " WHERE tenant_id = :tenant_id"
            params["tenant_id"] = str(tenant_id)
        sql += " ORDER BY created_at DESC LIMIT :limit"
        rows = (await self.db.execute(text(sql), params)).fetchall()
        return [dict(r._mapping) for r in rows]
