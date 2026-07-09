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

    async def get_query(self, query_id: UUID) -> Optional[dict]:
        result = await self.db.execute(
            text("SELECT * FROM query_logs WHERE id = :id"),
            {"id": str(query_id)},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None
