"""
Route wiring test: POST /v1/documents/index no longer returns 501 and correctly
drives the indexing service. The indexer is mocked (no real embeddings/DB).
"""
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.routes import documents as documents_route


@pytest.fixture
def client_with_mock_indexer(monkeypatch):
    mock_indexer = MagicMock()
    mock_indexer.index_document = AsyncMock(
        return_value={"status": "indexed", "chunks": 3, "checksum": "abc123"}
    )
    monkeypatch.setattr(documents_route, "get_indexer", lambda: mock_indexer)
    return TestClient(create_app()), mock_indexer


def test_index_document_success(client_with_mock_indexer):
    client, mock_indexer = client_with_mock_indexer

    resp = client.post(
        "/v1/documents/index",
        json={
            "source_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "content": "Paris is the capital and largest city of France.",
            "title": "France facts",
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["indexing_status"] == "indexed"
    assert body["estimated_chunks"] == 3
    assert body["document_id"]

    # Title + document_id must be threaded into indexer metadata.
    _, kwargs = mock_indexer.index_document.call_args
    assert kwargs["metadata"]["title"] == "France facts"
    assert kwargs["tenant_id"]


def test_index_rejects_empty_content(client_with_mock_indexer):
    client, mock_indexer = client_with_mock_indexer

    resp = client.post(
        "/v1/documents/index",
        json={
            "source_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "external_url": "https://example.com/article",
        },
    )

    assert resp.status_code == 400
    mock_indexer.index_document.assert_not_called()


def test_index_already_indexed_is_reported(client_with_mock_indexer):
    client, mock_indexer = client_with_mock_indexer
    mock_indexer.index_document = AsyncMock(
        return_value={"status": "already_indexed", "checksum": "abc123"}
    )

    resp = client.post(
        "/v1/documents/index",
        json={
            "source_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "content": "Duplicate content.",
        },
    )

    assert resp.status_code == 202
    assert resp.json()["indexing_status"] == "already_indexed"


def test_indexer_error_surfaces_as_500(client_with_mock_indexer):
    client, mock_indexer = client_with_mock_indexer
    mock_indexer.index_document = AsyncMock(side_effect=RuntimeError("embedder down"))

    resp = client.post(
        "/v1/documents/index",
        json={
            "source_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "content": "Some content.",
        },
    )

    assert resp.status_code == 500
    assert "Indexing error" in resp.json()["detail"]
