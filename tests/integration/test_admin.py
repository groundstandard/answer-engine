"""Phase 2 admin review queue — validation + wiring."""
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.app import create_app


def test_resolve_rejects_bad_status():
    client = TestClient(create_app())
    r = client.post(f"/v1/admin/reviews/{uuid4()}/resolve", json={"status": "nope"})
    assert r.status_code == 400
    assert "status must be one of" in r.json()["detail"]
