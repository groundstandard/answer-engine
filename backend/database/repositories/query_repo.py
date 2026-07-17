import json
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class QueryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_query(
        self,
        query_id: UUID,
        tenant_id: UUID,
        query_text: str,
        final_decision: str,
        user_id: Optional[UUID] = None,
        policy_profile: str = "default",
        latency_ms: Optional[int] = None,
        model_calls: Optional[int] = None,
        tokens_used: Optional[int] = None,
        trace: Optional[dict] = None,
    ) -> None:
        """Persist a query log with its full pipeline trace (PRD Section 12, Phase 1)."""
        await self.db.execute(
            text("""
                INSERT INTO query_logs
                    (id, tenant_id, user_id, query_text, final_decision,
                     policy_profile, latency_ms, model_calls, tokens_used, trace, created_at)
                VALUES
                    (:id, :tenant_id, :user_id, :query_text, :decision,
                     :profile, :latency_ms, :model_calls, :tokens_used, CAST(:trace AS JSONB), NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(query_id),
                "tenant_id": str(tenant_id),
                "user_id": str(user_id) if user_id else None,
                "query_text": query_text,
                "decision": final_decision,
                "profile": policy_profile,
                "latency_ms": latency_ms,
                "model_calls": model_calls,
                "tokens_used": tokens_used,
                "trace": json.dumps(trace, default=str) if trace is not None else None,
            },
        )
        await self.db.commit()

    async def list_for_tenant(self, tenant_id: UUID, limit: int, offset: int) -> list[dict]:
        """Recent query logs for a tenant, newest first (paginated)."""
        result = await self.db.execute(
            text("""
                SELECT id, query_text, final_decision, policy_profile,
                       latency_ms, created_at
                FROM query_logs
                WHERE tenant_id = :tid
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"tid": str(tenant_id), "limit": limit, "offset": offset},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def list_grouped_for_tenant(self, tenant_id: UUID, limit: int, offset: int) -> list[dict]:
        """One entry per distinct question, with every run collapsed into run_list."""
        result = await self.db.execute(
            text("""
                SELECT query_text,
                       COUNT(*) AS runs,
                       MAX(created_at) AS last_at,
                       (ARRAY_AGG(policy_profile ORDER BY created_at DESC))[1] AS policy_profile,
                       JSON_AGG(JSON_BUILD_OBJECT(
                           'id', id, 'decision', final_decision,
                           'latency_ms', latency_ms, 'created_at', created_at
                       ) ORDER BY created_at DESC) AS run_list
                FROM query_logs
                WHERE tenant_id = :tid
                GROUP BY query_text
                ORDER BY MAX(created_at) DESC
                LIMIT :limit OFFSET :offset
            """),
            {"tid": str(tenant_id), "limit": limit, "offset": offset},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def count_distinct_for_tenant(self, tenant_id: UUID) -> int:
        result = await self.db.execute(
            text("SELECT COUNT(DISTINCT query_text) FROM query_logs WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        )
        return int(result.scalar() or 0)

    async def count_for_tenant(self, tenant_id: UUID) -> int:
        result = await self.db.execute(
            text("SELECT COUNT(*) FROM query_logs WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        )
        return int(result.scalar() or 0)

    async def get_query(self, query_id: UUID) -> Optional[dict]:
        result = await self.db.execute(
            text("SELECT * FROM query_logs WHERE id = :id"),
            {"id": str(query_id)},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None
