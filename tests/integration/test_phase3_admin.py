"""Phase 3 admin surfaces: audit / freshness / calibration / assign are wired."""
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.app import create_app


def test_freshness_requires_tenant():
    client = TestClient(create_app())
    assert client.get("/v1/admin/freshness").status_code == 422


def test_calibration_requires_tenant():
    client = TestClient(create_app())
    assert client.get("/v1/admin/calibration").status_code == 422


def test_assign_requires_reviewer_id():
    client = TestClient(create_app())
    # missing reviewer_id in body -> validation error (route is wired)
    assert client.post(f"/v1/admin/reviews/{uuid4()}/assign", json={}).status_code == 422
