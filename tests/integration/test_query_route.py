"""
Route wiring test: POST /v1/query no longer returns 501 and correctly maps a
pipeline FinalResponse into the public QueryResponse schema.

The pipeline is mocked (no real LLM/DB), and the DB is expected to be down — the
best-effort trace logger must swallow that and still return the response
(PRD 2.1: synchronous pipeline, asynchronous logging).
"""
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.routes import query as query_route
from backend.models.response import FinalResponse, Citation


@pytest.fixture
def client_with_mock_pipeline(monkeypatch):
    evidence_id = uuid4()
    claim_id = uuid4()

    mock_final = FinalResponse(
        query_id=uuid4(),
        final_decision="VERIFIED",
        response_text="Paris is the capital of France.",
        confidence_summary="All critical claims supported.",
        citations=[
            Citation(
                citation_id=uuid4(),
                claim_id=claim_id,
                evidence_id=evidence_id,
                source_name="World Atlas",
                source_url="https://example.com/atlas",
                snippet="Paris is the capital and largest city of France.",
                trust_tier=1,
            )
        ],
        uncertainty_notes=[],
        trace_id=uuid4(),
        latency_ms=42,
    )

    mock_pipeline = MagicMock()
    mock_pipeline.run_pipeline = AsyncMock(return_value=mock_final)

    # Bypass the cached real pipeline (which would build an Anthropic client).
    monkeypatch.setattr(query_route, "get_pipeline", lambda: mock_pipeline)

    return TestClient(create_app()), mock_pipeline


def test_query_returns_verified_response(client_with_mock_pipeline):
    client, mock_pipeline = client_with_mock_pipeline

    resp = client.post(
        "/v1/query",
        json={
            "query": "What is the capital of France?",
            "tenant_id": str(uuid4()),
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["final_decision"] == "VERIFIED"
    assert body["response_text"] == "Paris is the capital of France."
    assert len(body["citations"]) == 1
    assert body["citations"][0]["source_name"] == "World Atlas"
    assert body["latency_ms"] == 42
    # query_id is overridden by the route (not the composer's throwaway id).
    assert body["query_id"]
    mock_pipeline.run_pipeline.assert_awaited_once()


def test_query_maps_domain_to_policy_profile(client_with_mock_pipeline):
    client, mock_pipeline = client_with_mock_pipeline

    resp = client.post(
        "/v1/query",
        json={
            "query": "Is ibuprofen safe with aspirin?",
            "tenant_id": str(uuid4()),
            "domain_hint": "medical",
        },
    )

    assert resp.status_code == 200, resp.text
    # The stricter 'medical' policy profile must have been passed to the pipeline.
    _, kwargs = mock_pipeline.run_pipeline.call_args
    assert kwargs["policy_config"].minimum_claim_support_ratio == 0.97


def test_pipeline_error_surfaces_as_500(client_with_mock_pipeline, monkeypatch):
    client, mock_pipeline = client_with_mock_pipeline
    mock_pipeline.run_pipeline = AsyncMock(side_effect=RuntimeError("model down"))

    resp = client.post(
        "/v1/query",
        json={"query": "anything", "tenant_id": str(uuid4())},
    )

    # PRD 3.1: never a silent fallback — a pipeline failure is a structured 5xx.
    assert resp.status_code == 500
    assert "Pipeline error" in resp.json()["detail"]
