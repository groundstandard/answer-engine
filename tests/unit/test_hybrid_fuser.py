import pytest
from uuid import uuid4
from backend.services.retrieval.hybrid_fuser import HybridFuser
from backend.models.evidence import EvidenceItem


def make_item(trust=0.8, freshness=0.7):
    return EvidenceItem(
        evidence_id=uuid4(),
        source_id=uuid4(),
        content="Test content",
        source_name="Source",
        trust_score=trust,
        freshness_score=freshness,
        trust_tier=2,
    )


class TestHybridFuser:
    def setup_method(self):
        self.fuser = HybridFuser()

    def test_fuse_deduplicates_overlapping_results(self):
        shared_item = make_item()
        vector_results = [shared_item, make_item()]
        bm25_results = [shared_item, make_item()]

        fused = self.fuser.fuse(vector_results, bm25_results, top_k=10)
        ids = [str(e.evidence_id) for e in fused]
        assert len(ids) == len(set(ids)), "Duplicate evidence items in fused results"

    def test_fuse_respects_top_k(self):
        vector_results = [make_item() for _ in range(10)]
        bm25_results = [make_item() for _ in range(10)]

        fused = self.fuser.fuse(vector_results, bm25_results, top_k=5)
        assert len(fused) <= 5

    def test_shared_item_ranks_higher(self):
        shared = make_item()
        vector_results = [make_item(), make_item(), shared]
        bm25_results = [make_item(), shared]

        fused = self.fuser.fuse(vector_results, bm25_results, top_k=10)
        first_id = str(fused[0].evidence_id)
        assert first_id == str(shared.evidence_id), "Shared item should have highest RRF score"

    def test_empty_inputs_returns_empty(self):
        assert self.fuser.fuse([], [], top_k=10) == []
