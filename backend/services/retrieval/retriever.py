from uuid import UUID
from typing import Optional, List
from backend.models.evidence import EvidenceBundle, EvidenceItem
from backend.models.classification import ClassificationResult
from backend.config.settings import settings


class RetrievalService:
    """
    Hybrid retrieval: vector similarity + BM25 keyword search fused via RRF,
    with an optional LLM-based rerank pass (ENABLE_RERANKER).
    """

    def __init__(self):
        from backend.services.retrieval.vector_search import VectorSearchEngine
        from backend.services.retrieval.bm25_search import BM25SearchEngine
        from backend.services.retrieval.hybrid_fuser import HybridFuser
        from backend.services.retrieval.trust_filter import TrustFilter
        from backend.services.retrieval.freshness_filter import FreshnessFilter
        from backend.services.retrieval.query_rewriter import QueryRewriter

        self.vector = VectorSearchEngine()
        self.bm25 = BM25SearchEngine()
        self.fuser = HybridFuser()
        self.trust_filter = TrustFilter()
        self.freshness_filter = FreshnessFilter()
        self.query_rewriter = QueryRewriter()
        self.reranker = None
        if settings.ENABLE_RERANKER:
            from backend.services.retrieval.reranker import Reranker
            self.reranker = Reranker()

    async def retrieve_evidence(
        self,
        query: str,
        classification: ClassificationResult,
        tenant_id: UUID,
        source_scope: Optional[List[UUID]] = None,
        top_k: int = 20,
    ) -> EvidenceBundle:
        rewritten_queries = await self.query_rewriter.rewrite(
            query=query,
            domain=classification.domain,
            n_variants=3,
        )

        vector_hits = await self.vector.search(
            query=query,
            rewritten_queries=rewritten_queries,
            tenant_id=tenant_id,
            source_scope=source_scope,
            top_k=top_k,
        )

        bm25_hits = await self.bm25.search(
            query=query,
            tenant_id=tenant_id,
            source_scope=source_scope,
            top_k=top_k,
        )

        fused = self.fuser.fuse(vector_results=vector_hits, bm25_results=bm25_hits, top_k=top_k)
        filtered = self.trust_filter.filter(fused)
        filtered = self.freshness_filter.filter(filtered)

        # Optional LLM rerank pass over the surviving candidates.
        if self.reranker and filtered:
            filtered = await self.reranker.rerank(query, filtered, top_k=top_k)

        return EvidenceBundle(
            query_id=None,
            evidence_items=filtered,
            retrieval_latency_ms=0,
            total_candidates_before_filter=len(vector_hits) + len(bm25_hits),
        )
