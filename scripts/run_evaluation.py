#!/usr/bin/env python3
"""
Run a golden evaluation dataset through the pipeline.

Usage:
    python scripts/run_evaluation.py <dataset> <tenant_id> [--profile default|high_risk|medical]

Datasets: factual | unanswerable | conflicting  (see evaluation_datasets/)
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    from backend.services.evaluation.datasets import load_dataset, list_datasets
    from backend.services.evaluation.runner import EvaluationRunner
    from backend.api.schemas.evaluations import EvaluationRunRequest

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    profile = "default"
    for a in sys.argv[1:]:
        if a.startswith("--profile"):
            profile = a.split("=", 1)[1] if "=" in a else "default"

    if len(args) < 2:
        print(f"Usage: run_evaluation.py <dataset> <tenant_id> [--profile=NAME]")
        print(f"Datasets: {', '.join(list_datasets())}")
        return

    dataset_name, tenant_id = args[0], args[1]
    dataset = load_dataset(dataset_name)
    print(f"Dataset: {dataset['name']} — {len(dataset['cases'])} cases")

    runner = EvaluationRunner()
    request = EvaluationRunRequest(
        tenant_id=tenant_id,
        test_cases=dataset["cases"],
        policy_profile=profile,
    )
    result = await runner.run(request)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
