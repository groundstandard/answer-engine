from uuid import UUID, uuid4
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class ReviewRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue(
        self,
        tenant_id: UUID,
        query_text: str,
        reason: Optional[str],
        query_log_id: Optional[UUID] = None,
    ) -> UUID:
        review_id = uuid4()
        await self.db.execute(
            text("""
                INSERT INTO review_queue (id, query_log_id, tenant_id, query_text, reason, status)
                VALUES (:id, :qlid, :tenant_id, :query_text, :reason, 'pending')
            """),
            {
                "id": str(review_id),
                "qlid": str(query_log_id) if query_log_id else None,
                "tenant_id": str(tenant_id),
                "query_text": query_text,
                "reason": reason,
            },
        )
        await self.db.commit()
        return review_id

    async def list_reviews(self, tenant_id: Optional[UUID], status: str) -> List[dict]:
        sql = """
            SELECT id, query_log_id, tenant_id, query_text, reason, status,
                   resolution_note, created_at, resolved_at
            FROM review_queue
            WHERE status = :status
        """
        params = {"status": status}
        if tenant_id:
            sql += " AND tenant_id = :tenant_id"
            params["tenant_id"] = str(tenant_id)
        sql += " ORDER BY created_at DESC LIMIT 200"
        rows = (await self.db.execute(text(sql), params)).fetchall()
        return [dict(r._mapping) for r in rows]

    async def resolve(self, review_id: UUID, status: str, note: Optional[str]) -> bool:
        result = await self.db.execute(
            text("""
                UPDATE review_queue
                SET status = :status, resolution_note = :note, resolved_at = NOW()
                WHERE id = :id AND status = 'pending'
            """),
            {"id": str(review_id), "status": status, "note": note},
        )
        await self.db.commit()
        return result.rowcount > 0
