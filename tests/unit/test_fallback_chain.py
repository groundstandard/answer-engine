"""Model transport fallback chain (n8n -> Anthropic SDK)."""
from unittest.mock import AsyncMock

import pytest

from backend.orchestration.model_client import ModelClient


def _bare_client():
    # Bypass __init__ so we don't construct real network clients.
    return ModelClient.__new__(ModelClient)


@pytest.mark.asyncio
async def test_falls_back_to_anthropic_when_n8n_fails():
    mc = _bare_client()
    mc._webhook_url = "http://n8n.test/webhook"
    mc._anthropic = object()  # truthy -> anthropic transport is in the chain
    mc._call_n8n = AsyncMock(side_effect=RuntimeError("n8n down"))
    mc._call_anthropic = AsyncMock(return_value='{"draft_answer": "ok"}')

    out = await mc.call("DRAFT", {"query": "x"})

    assert out == {"draft_answer": "ok"}
    mc._call_n8n.assert_awaited_once()
    mc._call_anthropic.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_transports_failing_raises():
    mc = _bare_client()
    mc._webhook_url = "http://n8n.test/webhook"
    mc._anthropic = object()
    mc._call_n8n = AsyncMock(side_effect=RuntimeError("n8n down"))
    mc._call_anthropic = AsyncMock(side_effect=RuntimeError("sdk down"))

    with pytest.raises(RuntimeError, match="All LLM transports failed"):
        await mc.call("DRAFT", {"query": "x"})


@pytest.mark.asyncio
async def test_no_transport_configured_raises():
    mc = _bare_client()
    mc._webhook_url = ""
    mc._anthropic = None
    with pytest.raises(RuntimeError, match="No LLM transport"):
        await mc.call("DRAFT", {"query": "x"})
