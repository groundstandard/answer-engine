import time
from uuid import UUID, uuid4
from typing import List

from backend.api.schemas.evaluations import EvaluationRunRequest, EvaluationResult
from backend.config.policy_loader import load_policy_config


class EvaluationRunner:
    """Runs a batch of golden queries through the real pipeline and scores them."""

    def __init__(self, pipeline=None):
        # Lazy import avoids a circular import (routes -> runner -> routes).
        if pipeline is None:
            from backend.api.routes.query import get_pipeline
            pipeline = get_pipeline()
        self.pipeline = pipeline

    async def run(self, request: EvaluationRunRequest) -> dict:
        evaluation_id = uuid4()
        policy_config = load_policy_config(request.policy_profile)
        results: List[EvaluationResult] = []

        for test_case in request.test_cases:
            results.append(await self._run_single(test_case, request.tenant_id, policy_config))

        passed = sum(1 for r in results if r.passed)
        total = len(results)

        return {
            "evaluation_id": str(evaluation_id),
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "accuracy": passed / total if total else 0.0,
            "results": [r.__dict__ for r in results],
        }

    async def _run_single(self, test_case: dict, tenant_id: UUID, policy_config) -> EvaluationResult:
        query = test_case.get("query", "")
        expected = test_case.get("expected_decision", "VERIFIED")
        case_id = test_case.get("id", str(uuid4()))
        start = time.monotonic()
        try:
            final = await self.pipeline.run_pipeline(
                query=query,
                tenant_id=tenant_id,
                user_id=None,
                policy_config=policy_config,
                domain_hint=test_case.get("domain_hint"),
            )
            actual = final.final_decision
            return EvaluationResult(
                test_case_id=case_id,
                query=query,
                expected_decision=expected,
                actual_decision=actual,
                passed=(actual == expected),
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:  # noqa: BLE001 — a failed case is a data point, not a crash
            return EvaluationResult(
                test_case_id=case_id,
                query=query,
                expected_decision=expected,
                actual_decision="ERROR",
                passed=False,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
            )
