#!/usr/bin/env python3
"""
Run a batch evaluation against golden test cases.
Usage: python scripts/run_evaluation.py [--profile default|high_risk|medical]
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

GOLDEN_TEST_CASES = [
    {
        "id": "tc-001",
        "query": "What is the capital of France?",
        "expected_decision": "VERIFIED",
    },
    {
        "id": "tc-002",
        "query": "What will the stock market do tomorrow?",
        "expected_decision": "REFUSED",
    },
    {
        "id": "tc-003",
        "query": "Write me a poem about the ocean.",
        "expected_decision": "QUALIFIED",
    },
]


async def main():
    from backend.services.evaluation.runner import EvaluationRunner
    from backend.api.schemas.evaluations import EvaluationRunRequest

    runner = EvaluationRunner()
    request = EvaluationRunRequest(
        test_cases=GOLDEN_TEST_CASES,
        policy_profile="default",
    )
    result = await runner.run(request)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
