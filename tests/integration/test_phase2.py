"""Phase 2 tests: per-tenant policy resolution + rate limiting."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.routes import query as query_mod
from backend.api.schemas.query import QueryRequest
from backend.config.settings import settings
from backend.api.middleware.rate_limiter import rate_limiter


class _Boom:
    """Async context manager that fails — simulates DB unavailable."""
    async def __aenter__(self):
        raise RuntimeError("no db")

    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
async def test_domain_escalates_to_stricter_policy(monkeypatch):
    # DB lookup unavailable -> tenant profile falls back to 'default';
    # a medical domain hint must still escalate to the stricter medical policy.
    monkeypatch.setattr(query_mod, "AsyncSessionLocal", lambda: _Boom())
    req = QueryRequest(query="Is X safe?", tenant_id=uuid4(), domain_hint="medical")
    profile, cfg = await query_mod._resolve_policy(req)
    assert profile == "medical"
    assert cfg.minimum_claim_support_ratio == 0.97


@pytest.mark.asyncio
async def test_defaults_when_no_domain_and_no_db(monkeypatch):
    monkeypatch.setattr(query_mod, "AsyncSessionLocal", lambda: _Boom())
    req = QueryRequest(query="hello", tenant_id=uuid4())
    profile, cfg = await query_mod._resolve_policy(req)
    assert profile == "default"
    assert cfg.minimum_claim_support_ratio == 0.90


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    rate_limiter._counts.clear()
    client = TestClient(create_app())

    # Unmatched path still passes through the rate-limit middleware, so we can
    # exercise the limiter without touching the DB-backed routes.
    assert client.get("/v1/__ping").status_code == 404
    assert client.get("/v1/__ping").status_code == 404
    assert client.get("/v1/__ping").status_code == 429


def test_health_is_exempt_from_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    rate_limiter._counts.clear()
    client = TestClient(create_app())
    for _ in range(5):
        assert client.get("/health").status_code == 200
