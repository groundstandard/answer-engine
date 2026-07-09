from fastapi.testclient import TestClient

from backend.api.app import create_app


def test_dashboard_page_served():
    client = TestClient(create_app())
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Answer Engine" in r.text
