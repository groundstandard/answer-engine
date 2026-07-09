from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class EvaluationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_run(self, evaluation_id: UUID, total: int, passed: int, accuracy: float) -> None:
        await self.db.execute(
            text("""
                INSERT INTO evaluation_runs (id, total, passed, accuracy, created_at)
                VALUES (:id, :total, :passed, :accuracy, NOW())
            """),
            {"id": str(evaluation_id), "total": total, "passed": passed, "accuracy": accuracy},
        )
        await self.db.commit()

    async def get_run(self, evaluation_id: UUID) -> Optional[dict]:
        result = await self.db.execute(
            text("SELECT * FROM evaluation_runs WHERE id = :id"),
            {"id": str(evaluation_id)},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None
