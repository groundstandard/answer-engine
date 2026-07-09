import logging
from typing import List, Optional

from backend.models.evidence import EvidenceItem

logger = logging.getLogger(__name__)


class Reranker:
    """
    LLM-based reranker (no local model needed — runs through the n8n LLM webhook).

    Given a query and the fused candidate passages, it asks the model to order
    them by relevance and reorders accordingly. Resilient: on any failure it
    returns the candidates unchanged, so retrieval never breaks because of it.
    """

    def __init__(self, model_client=None):
        if model_client is None:
            from backend.orchestration.model_client import ModelClient
            model_client = ModelClient()
        self.model_client = model_client

    async def rerank(
        self, query: str, items: List[EvidenceItem], top_k: Optional[int] = None
    ) -> List[EvidenceItem]:
        if len(items) <= 1:
            return items[:top_k] if top_k else items

        listing = "\n".join(f"[{i + 1}] {it.content[:400]}" for i, it in enumerate(items))
        try:
            raw = await self.model_client.call(
                task_type="RERANK",
                prompt_inputs={"query": query, "candidates": listing, "n": len(items)},
                system_prompt=RERANK_SYSTEM_PROMPT,
            )
            ordered = self._apply_order(items, raw.get("ranking"))
        except Exception as e:  # noqa: BLE001 — reranking is best-effort
            logger.warning("Rerank skipped (falling back to fused order): %s", e)
            ordered = items

        # Assign a descending relevance score reflecting the new order.
        n = len(ordered)
        for rank, it in enumerate(ordered):
            it.relevance_score = (n - rank) / n

        return ordered[:top_k] if top_k else ordered

    @staticmethod
    def _apply_order(items: List[EvidenceItem], order) -> List[EvidenceItem]:
        if not isinstance(order, list):
            return items
        seen = set()
        result: List[EvidenceItem] = []
        for idx in order:
            try:
                i = int(idx) - 1
            except (ValueError, TypeError):
                continue
            if 0 <= i < len(items) and i not in seen:
                result.append(items[i])
                seen.add(i)
        # Keep any candidate the model didn't rank, in original order.
        for i, it in enumerate(items):
            if i not in seen:
                result.append(it)
        return result


RERANK_SYSTEM_PROMPT = """You rerank candidate evidence passages by how well each answers the query.
The candidates are numbered "[N]". Return JSON:
{ "ranking": [most relevant source number, ..., least relevant] }
Include every source number exactly once. Return valid JSON only."""
