from typing import List
from backend.models.evidence import EvidenceItem


class HybridFuser:
    """Reciprocal Rank Fusion (RRF) merges vector and BM25 result lists."""

    def fuse(
        self,
        vector_results: List[EvidenceItem],
        bm25_results: List[EvidenceItem],
        top_k: int = 20,
        k: int = 60,
    ) -> List[EvidenceItem]:
        scores: dict[str, float] = {}
        item_map: dict[str, EvidenceItem] = {}

        for rank, item in enumerate(vector_results, start=1):
            key = str(item.evidence_id)
            scores[key] = scores.get(key, 0.0) + 1 / (k + rank)
            item_map[key] = item

        for rank, item in enumerate(bm25_results, start=1):
            key = str(item.evidence_id)
            scores[key] = scores.get(key, 0.0) + 1 / (k + rank)
            item_map[key] = item

        ranked_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
        return [item_map[k] for k in ranked_keys[:top_k]]
