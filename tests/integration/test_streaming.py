"""Phase 3: SSE streaming endpoint /v1/query/stream."""
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.routes import query as query_mod
from backend.models.response import FinalResponse
from backend.models.policy import PolicyConfig


class _FakePipeline:
    async def run_pipeline(self, **kwargs):
        on_event = kwargs.get("on_event")
        if on_event:
            await on_event("classification", {"label": "LOW_RISK_FACTUAL"})
            await on_event("retrieval", {"evidence_count": 2})
            await on_event("verification", {"support_ratio": 1.0, "claims": []})
            await on_event("policy", {"decision": "ANSWER_VERIFIED"})
        return FinalResponse(
            query_id=uuid4(), final_decision="VERIFIED",
            response_text="Paris is the capital of France.",
            confidence_summary="ok", trace_id=uuid4(), latency_ms=5,
        )


def test_stream_emits_stage_events(monkeypatch):
    monkeypatch.setattr(query_mod, "get_pipeline", lambda: _FakePipeline())
    monkeypatch.setattr(query_mod, "_resolve_policy", AsyncMock(return_value=("default", PolicyConfig())))
    monkeypatch.setattr(query_mod, "_resolve_model_overrides", AsyncMock(return_value={}))
    monkeypatch.setattr(query_mod, "_log_query_trace", AsyncMock())

    client = TestClient(create_app())
    r = client.post("/v1/query/stream", json={"query": "capital of France?", "tenant_id": str(uuid4())})

    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    body = r.text
    for stage in ("classification", "retrieval", "verification", "policy", "final"):
        assert f"event: {stage}" in body
    assert "VERIFIED" in body
    assert "Paris is the capital of France." in body
