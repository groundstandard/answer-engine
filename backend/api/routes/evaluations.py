import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from backend.api.schemas.evaluations import EvaluationRunRequest, EvaluationRunResponse
from backend.services.evaluation.runner import EvaluationRunner
from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.evaluation_repo import EvaluationRepository

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/evaluations/run", response_model=EvaluationRunResponse, status_code=202)
async def run_evaluation(request: EvaluationRunRequest):
    """Run a batch of golden queries through the pipeline and score them."""
    if not request.test_cases:
        raise HTTPException(status_code=400, detail="test_cases must not be empty")

    try:
        summary = await EvaluationRunner().run(request)
    except Exception as e:  # noqa: BLE001
        logger.exception("Evaluation run failed")
        raise HTTPException(status_code=500, detail=f"Evaluation error: {e}")

    # Best-effort persistence (async logging — never breaks the response).
    try:
        async with AsyncSessionLocal() as session:
            await EvaluationRepository(session).save_run(
                evaluation_id=UUID(summary["evaluation_id"]),
                total=summary["total"],
                passed=summary["passed"],
                accuracy=summary["accuracy"],
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("Evaluation run not persisted (DB unavailable): %s", e)

    return EvaluationRunResponse(
        evaluation_id=UUID(summary["evaluation_id"]),
        status="complete",
        total=summary["total"],
        passed=summary["passed"],
        accuracy=summary["accuracy"],
    )


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationRunResponse)
async def get_evaluation(evaluation_id: UUID):
    """Retrieve the summary for a completed evaluation run."""
    try:
        async with AsyncSessionLocal() as session:
            row = await EvaluationRepository(session).get_run(evaluation_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Evaluation store unavailable: {e}")

    if not row:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    return EvaluationRunResponse(
        evaluation_id=evaluation_id,
        status="complete",
        total=row["total"],
        passed=row["passed"],
        accuracy=row["accuracy"],
    )
