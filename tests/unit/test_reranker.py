"""Unit tests for the LLM-based reranker."""
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.retrieval.reranker import Reranker
from backend.models.evidence import EvidenceItem


def _item(content):
    return EvidenceItem(
        evidence_id=uuid4(), source_id=uuid4(), content=content,
        source_name="s", trust_score=0.8, freshness_score=1.0, trust_tier=4,
    )


def test_apply_order_reorders():
    items = [_item("a"), _item("b"), _item("c")]
    out = Reranker._apply_order(items, [3, 1, 2])
    assert [i.content for i in out] == ["c", "a", "b"]


def test_apply_order_appends_unranked():
    items = [_item("a"), _item("b"), _item("c")]
    out = Reranker._apply_order(items, [2])  # model only ranked one
    assert [i.content for i in out] == ["b", "a", "c"]


def test_apply_order_ignores_bad_indices():
    items = [_item("a"), _item("b")]
    out = Reranker._apply_order(items, [99, "x", 2, 1])
    assert [i.content for i in out] == ["b", "a"]


def test_apply_order_bad_input_returns_unchanged():
    items = [_item("a"), _item("b")]
    assert Reranker._apply_order(items, None) is items


@pytest.mark.asyncio
async def test_rerank_applies_model_ranking():
    items = [_item("a"), _item("b")]
    mc = MagicMock()
    mc.call = AsyncMock(return_value={"ranking": [2, 1]})
    out = await Reranker(model_client=mc).rerank("q", items)
    assert [i.content for i in out] == ["b", "a"]
    assert out[0].relevance_score > out[1].relevance_score


@pytest.mark.asyncio
async def test_rerank_falls_back_on_error():
    items = [_item("a"), _item("b")]
    mc = MagicMock()
    mc.call = AsyncMock(side_effect=RuntimeError("llm down"))
    out = await Reranker(model_client=mc).rerank("q", items)
    assert [i.content for i in out] == ["a", "b"]  # original order preserved
