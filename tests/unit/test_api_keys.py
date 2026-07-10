"""API-key auth: hashing, generation, and mint validation."""
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.database.repositories.api_key_repo import hash_key, generate_key


def test_hash_is_deterministic_and_distinct():
    assert hash_key("abc") == hash_key("abc")
    assert hash_key("abc") != hash_key("abd")


def test_generate_key_format_and_uniqueness():
    k = generate_key()
    assert k.startswith("ae_") and len(k) > 20
    assert generate_key() != generate_key()


def test_mint_rejects_bad_role():
    client = TestClient(create_app())
    r = client.post("/v1/auth/api-keys", json={"tenant_id": str(uuid4()), "role": "root"})
    assert r.status_code == 400
