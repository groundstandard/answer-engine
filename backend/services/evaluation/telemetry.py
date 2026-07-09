import time
from uuid import UUID
from typing import Optional


class TelemetryRecorder:
    """Records pipeline events for evaluation and debugging."""

    async def record_query(
        self,
        query_id: UUID,
        tenant_id: UUID,
        query_text: str,
        final_decision: str,
        latency_ms: int,
        model_calls: int,
        tokens_used: int,
        trace: Optional[dict] = None,
    ) -> None:
        # Stub: production inserts into query_logs table
        pass

    async def record_feedback(
        self,
        query_id: UUID,
        rating: int,
        comment: Optional[str],
        user_id: Optional[UUID],
    ) -> None:
        # Stub: production inserts into feedback table
        pass
