"""
Wiring tests for the previously-stubbed routes: /v1/sources, /v1/feedback,
/v1/evaluations. Confirms they no longer return 501 and enforce validation.
DB-backed success paths are covered where mockable; validation paths need no DB.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.routes import evaluations as eval_route


@pytest.fixture
def client():
    return TestClient(create_app())


# ---- sources ----

def test_sources_create_rejects_bad_trust_tier(client):
    resp = client.post("/v1/sources", json={
        "tenant_id": str(uuid4()),
        "source_name": "Bad Source",
        "trust_tier": 9,
    })
    assert resp.status_code == 400  # validation runs before any DB access
    assert "trust_tier" in resp.json()["detail"]


def test_sources_list_requires_tenant_id(client):
    resp = client.get("/v1/sources")
    assert resp.status_code == 422  # missing required query param — route is wired


# ---- feedback ----

def test_feedback_rejects_bad_rating(client):
    resp = client.post("/v1/feedback", json={
        "query_id": str(uuid4()),
        "rating": 9,
    })
    assert resp.status_code == 400
    assert "rating" in resp.json()["detail"]


# ---- evaluations ----

def test_evaluation_rejects_empty_cases(client):
    resp = client.post("/v1/evaluations/run", json={
        "tenant_id": str(uuid4()),
        "test_cases": [],
    })
    assert resp.status_code == 400


def test_evaluation_runs_with_mocked_runner(client, monkeypatch):
    class FakeRunner:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, request):
            return {
                "evaluation_id": str(uuid4()),
                "total": 2, "passed": 2, "failed": 0, "accuracy": 1.0, "results": [],
            }

    monkeypatch.setattr(eval_route, "EvaluationRunner", FakeRunner)

    resp = client.post("/v1/evaluations/run", json={
        "tenant_id": str(uuid4()),
        "test_cases": [
            {"id": "t1", "query": "capital of France?", "expected_decision": "VERIFIED"},
            {"id": "t2", "query": "capital of Japan?", "expected_decision": "VERIFIED"},
        ],
    })
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "complete"
    assert body["total"] == 2
    assert body["accuracy"] == 1.0
