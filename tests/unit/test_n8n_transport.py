"""
Unit tests for n8n webhook transport in ModelClient and Embedder.
Verifies that when a webhook URL is configured, calls are POSTed to n8n and
the response is parsed from the agreed contract shape.
"""
import json

import pytest

from backend.config.settings import settings
from backend.orchestration import model_client as mc_mod
from backend.orchestration.model_client import ModelClient
from backend.services.indexing import embedder as emb_mod
from backend.services.indexing.embedder import Embedder


class _FakeResp:
    def __init__(self, json_data):
        self._j = json_data
        self.text = json.dumps(json_data)

    def raise_for_status(self):
        pass

    def json(self):
        return self._j


def _make_fake_client(captured, response_json):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers
            return _FakeResp(response_json)

    return _FakeClient


@pytest.mark.asyncio
async def test_model_client_routes_through_n8n(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings, "N8N_LLM_WEBHOOK_URL", "http://n8n.test/webhook/llm")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_AUTH_HEADER", "X-Api-Key")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_AUTH_TOKEN", "secret123")
    monkeypatch.setattr(
        mc_mod, "httpx",
        type("m", (), {"AsyncClient": _make_fake_client(captured, {"text": '{"draft_answer": "Paris."}'}),
                       "Response": object})(),
    )

    client = ModelClient()
    result = await client.call(task_type="DRAFT", prompt_inputs={"query": "capital of France?"})

    assert result == {"draft_answer": "Paris."}
    assert captured["url"] == "http://n8n.test/webhook/llm"
    assert captured["payload"]["task_type"] == "DRAFT"
    assert captured["headers"]["X-Api-Key"] == "secret123"


@pytest.mark.asyncio
async def test_model_client_extracts_anthropic_style_content(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings, "N8N_LLM_WEBHOOK_URL", "http://n8n.test/webhook/llm")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_AUTH_HEADER", "")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_AUTH_TOKEN", "")
    monkeypatch.setattr(
        mc_mod, "httpx",
        type("m", (), {"AsyncClient": _make_fake_client(captured, {"content": [{"text": '{"claims": []}'}]}),
                       "Response": object})(),
    )

    client = ModelClient()
    result = await client.call(task_type="EXTRACT_CLAIMS", prompt_inputs={"draft_answer": "x"})
    assert result == {"claims": []}


@pytest.mark.asyncio
async def test_embedder_routes_through_n8n(monkeypatch):
    captured = {}
    vec = [0.1] * 1536
    monkeypatch.setattr(settings, "N8N_EMBEDDING_WEBHOOK_URL", "http://n8n.test/webhook/embed")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_AUTH_HEADER", "")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_AUTH_TOKEN", "")
    monkeypatch.setattr(
        emb_mod, "httpx",
        type("m", (), {"AsyncClient": _make_fake_client(captured, {"embeddings": [vec]})})(),
    )

    embedder = Embedder()
    result = await embedder.embed_query("hello world")

    assert result == vec
    assert captured["url"] == "http://n8n.test/webhook/embed"
    assert captured["payload"]["input"] == ["hello world"]


@pytest.mark.asyncio
async def test_embedder_rejects_bad_shape(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings, "N8N_EMBEDDING_WEBHOOK_URL", "http://n8n.test/webhook/embed")
    monkeypatch.setattr(settings, "MAX_MODEL_RETRIES", 1)
    monkeypatch.setattr(
        emb_mod, "httpx",
        type("m", (), {"AsyncClient": _make_fake_client(captured, {"embeddings": []})})(),
    )

    embedder = Embedder()
    with pytest.raises(RuntimeError, match="embedding webhook failed"):
        await embedder.embed_query("mismatch")
