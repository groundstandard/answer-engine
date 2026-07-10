from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.app import create_app


def test_delete_source_requires_tenant():
    client = TestClient(create_app())
    # missing tenant_id query param -> validation error (route is wired)
    assert client.delete(f"/v1/sources/{uuid4()}").status_code == 422
