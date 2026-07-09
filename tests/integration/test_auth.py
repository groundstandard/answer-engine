"""Phase 2 auth: token minting + optional enforcement."""
from uuid import uuid4

from fastapi.testclient import TestClient
from jose import jwt

from backend.api.app import create_app
from backend.config.settings import settings


def test_mint_token_and_claims():
    client = TestClient(create_app())
    tenant = str(uuid4())
    r = client.post("/v1/auth/token", json={"tenant_id": tenant})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    claims = jwt.decode(tok, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert claims["tenant_id"] == tenant
    assert "exp" in claims


def test_service_key_guards_minting(monkeypatch):
    monkeypatch.setattr(settings, "SERVICE_KEY", "s3cret")
    client = TestClient(create_app())
    body = {"tenant_id": str(uuid4())}

    assert client.post("/v1/auth/token", json=body).status_code == 403
    assert client.post("/v1/auth/token", json=body, headers={"X-Service-Key": "wrong"}).status_code == 403
    ok = client.post("/v1/auth/token", json=body, headers={"X-Service-Key": "s3cret"})
    assert ok.status_code == 200


def test_auth_required_blocks_without_token(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    client = TestClient(create_app())
    r = client.get(f"/v1/metrics?tenant_id={uuid4()}")
    assert r.status_code == 401


def test_auth_required_allows_valid_token(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    client = TestClient(create_app())
    tok = client.post("/v1/auth/token", json={"tenant_id": str(uuid4())}).json()["access_token"]
    r = client.get(f"/v1/metrics?tenant_id={uuid4()}", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code != 401  # passed the auth gate (200 from live metrics)


def test_default_no_auth_required():
    # Default AUTH_REQUIRED=False -> minting open, guarded routes reachable.
    client = TestClient(create_app())
    r = client.post("/v1/auth/token", json={"tenant_id": str(uuid4())})
    assert r.status_code == 200
