"""Unit tests for evidence-id resolution (citation traceability)."""
from uuid import uuid4

from backend.services.verification.verifier import ClaimVerificationService
from backend.models.verification import VerificationStatus
from backend.models.evidence import EvidenceItem


def _item(content):
    return EvidenceItem(
        evidence_id=uuid4(), source_id=uuid4(), content=content,
        source_name="Src", trust_score=0.8, freshness_score=1.0, trust_tier=4,
    )


def _svc():
    return ClaimVerificationService(model_client=None)


def test_uses_supporting_source_index():
    items = [_item("alpha"), _item("beta"), _item("gamma")]
    ids = _svc()._resolve_evidence_ids(
        {"supporting_source": "2"}, VerificationStatus.SUPPORTED_DIRECT, None, items
    )
    assert ids == [items[1].evidence_id]


def test_falls_back_to_snippet_match():
    items = [_item("the sky is blue"), _item("grass is green")]
    ids = _svc()._resolve_evidence_ids(
        {"supporting_source": None}, VerificationStatus.SUPPORTED_PARAPHRASE,
        "GRASS is green", items,
    )
    assert ids == [items[1].evidence_id]


def test_falls_back_to_top_source_when_nothing_matches():
    items = [_item("alpha"), _item("beta")]
    ids = _svc()._resolve_evidence_ids(
        {}, VerificationStatus.SUPPORTED_INFERRED, "no match here", items
    )
    assert ids == [items[0].evidence_id]


def test_no_citation_when_unsupported():
    items = [_item("alpha")]
    ids = _svc()._resolve_evidence_ids(
        {"supporting_source": "1"}, VerificationStatus.UNSUPPORTED, None, items
    )
    assert ids == []


def test_no_citation_when_no_evidence():
    ids = _svc()._resolve_evidence_ids(
        {"supporting_source": "1"}, VerificationStatus.SUPPORTED_DIRECT, None, []
    )
    assert ids == []
