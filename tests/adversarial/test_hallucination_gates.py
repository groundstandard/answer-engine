"""
Adversarial tests: verify the policy engine refuses responses
when evidence is absent, stale, contradicted, or unsupported.
These tests exist to prevent hallucinations slipping through gates.
"""
import pytest
from uuid import uuid4
from backend.services.policy.engine import PolicyEngine
from backend.models.policy import PolicyConfig, PolicyDecisionType
from backend.models.classification import ClassificationResult
from backend.models.verification import VerificationResultSet, ClaimVerificationResult, VerificationStatus
from backend.models.evidence import EvidenceBundle, EvidenceItem


def verified_classification():
    return ClassificationResult(
        classification_label="FACTUAL", domain="medical",
        risk_level=0.9, requires_evidence=True,
        complexity_score=0.8, raw_label="FACTUAL",
    )


def empty_bundle():
    return EvidenceBundle(
        query_id=uuid4(), evidence_items=[],
        retrieval_latency_ms=0, total_candidates_before_filter=0,
    )


def stale_bundle():
    return EvidenceBundle(
        query_id=uuid4(),
        evidence_items=[
            EvidenceItem(
                evidence_id=uuid4(), source_id=uuid4(),
                content="Old content", source_name="Old Source",
                trust_score=0.9, freshness_score=0.1, trust_tier=1,
            )
            for _ in range(3)  # pass Gate 1 (count), fail Gate 2 (freshness)
        ],
        retrieval_latency_ms=0, total_candidates_before_filter=3,
    )


def full_contradiction_verification():
    return VerificationResultSet(
        claim_results=[
            ClaimVerificationResult(claim_id=uuid4(), status=VerificationStatus.CONTRADICTED, confidence=0.95)
        ],
        aggregate_support_ratio=0.0,
        contains_contradiction=True,
        critical_claims_supported=False,
    )


engine = PolicyEngine()
config = PolicyConfig()


class TestHallucinationGates:
    def test_refuse_zero_evidence(self):
        result = engine.apply_policy(verified_classification(), full_contradiction_verification(), empty_bundle(), config)
        assert result.decision in (
            PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            PolicyDecisionType.REFUSE_UNVERIFIABLE,
        )

    def test_refuse_stale_sources(self):
        vr = VerificationResultSet(
            claim_results=[ClaimVerificationResult(claim_id=uuid4(), status=VerificationStatus.SUPPORTED_DIRECT, confidence=0.9)],
            aggregate_support_ratio=1.0, contains_contradiction=False, critical_claims_supported=True,
        )
        result = engine.apply_policy(verified_classification(), vr, stale_bundle(), config)
        assert result.decision == PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE
        assert "STALE_EVIDENCE" in result.reason_codes

    def test_refuse_full_contradiction(self):
        good_bundle = EvidenceBundle(
            query_id=uuid4(),
            evidence_items=[
                EvidenceItem(
                    evidence_id=uuid4(), source_id=uuid4(),
                    content="Contradicting content", source_name="A",
                    trust_score=0.9, freshness_score=0.9, trust_tier=1,
                )
            ],
            retrieval_latency_ms=0, total_candidates_before_filter=1,
        )
        result = engine.apply_policy(verified_classification(), full_contradiction_verification(), good_bundle, config)
        assert result.decision != PolicyDecisionType.ANSWER_VERIFIED

    def test_refuse_unsupported_claims_below_floor(self):
        vr = VerificationResultSet(
            claim_results=[ClaimVerificationResult(claim_id=uuid4(), status=VerificationStatus.UNSUPPORTED, confidence=0.1)],
            aggregate_support_ratio=0.1, contains_contradiction=False, critical_claims_supported=False,
        )
        good_bundle = EvidenceBundle(
            query_id=uuid4(),
            evidence_items=[
                EvidenceItem(
                    evidence_id=uuid4(), source_id=uuid4(),
                    content="Relevant content", source_name="B",
                    trust_score=0.9, freshness_score=0.9, trust_tier=2,
                )
                for _ in range(3)
            ],
            retrieval_latency_ms=0, total_candidates_before_filter=3,
        )
        result = engine.apply_policy(verified_classification(), vr, good_bundle, config)
        assert result.decision in (
            PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            PolicyDecisionType.ESCALATE_HUMAN_REVIEW,
        )
