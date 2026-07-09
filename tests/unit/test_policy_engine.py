import pytest
from uuid import uuid4
from backend.services.policy.engine import PolicyEngine
from backend.models.policy import PolicyConfig, PolicyDecisionType
from backend.models.classification import ClassificationResult
from backend.models.verification import VerificationResultSet, ClaimVerificationResult, VerificationStatus
from backend.models.evidence import EvidenceBundle, EvidenceItem


def make_evidence(n=3, trust=0.8, freshness=0.8):
    return EvidenceBundle(
        query_id=uuid4(),
        evidence_items=[
            EvidenceItem(
                evidence_id=uuid4(),
                source_id=uuid4(),
                content=f"Evidence item {i}",
                source_name="Test Source",
                trust_score=trust,
                freshness_score=freshness,
                trust_tier=2,
            )
            for i in range(n)
        ],
        retrieval_latency_ms=50,
        total_candidates_before_filter=n,
    )


def make_verification(support_ratio=1.0, has_contradiction=False):
    claim_id = uuid4()
    status = VerificationStatus.SUPPORTED_DIRECT if support_ratio >= 1.0 else VerificationStatus.UNSUPPORTED
    return VerificationResultSet(
        claim_results=[ClaimVerificationResult(claim_id=claim_id, status=status, confidence=0.9)],
        aggregate_support_ratio=support_ratio,
        contains_contradiction=has_contradiction,
        critical_claims_supported=True,
    )


def make_classification(risk=0.3):
    return ClassificationResult(
        classification_label="FACTUAL",
        domain="general",
        risk_level=risk,
        requires_evidence=True,
        complexity_score=0.5,
        raw_label="FACTUAL",
    )


class TestPolicyEngine:
    def setup_method(self):
        self.engine = PolicyEngine()
        self.config = PolicyConfig()

    def test_verified_when_full_support(self):
        decision = self.engine.apply_policy(
            classification=make_classification(),
            verification_results=make_verification(support_ratio=1.0),
            evidence_bundle=make_evidence(n=3),
            policy_config=self.config,
        )
        assert decision.decision == PolicyDecisionType.ANSWER_VERIFIED

    def test_refuse_when_insufficient_evidence(self):
        decision = self.engine.apply_policy(
            classification=make_classification(),
            verification_results=make_verification(support_ratio=1.0),
            evidence_bundle=make_evidence(n=1),
            policy_config=self.config,
        )
        assert decision.decision == PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE
        assert "INSUFFICIENT_EVIDENCE_COUNT" in decision.reason_codes

    def test_refuse_when_low_trust(self):
        decision = self.engine.apply_policy(
            classification=make_classification(),
            verification_results=make_verification(support_ratio=1.0),
            evidence_bundle=make_evidence(n=3, trust=0.2),
            policy_config=self.config,
        )
        assert decision.decision == PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE
        assert "LOW_TRUST_EVIDENCE" in decision.reason_codes

    def test_qualified_when_partial_support(self):
        decision = self.engine.apply_policy(
            classification=make_classification(),
            verification_results=make_verification(support_ratio=0.75),
            evidence_bundle=make_evidence(n=3),
            policy_config=self.config,
        )
        assert decision.decision == PolicyDecisionType.ANSWER_QUALIFIED

    def test_refuse_when_support_below_floor(self):
        decision = self.engine.apply_policy(
            classification=make_classification(),
            verification_results=make_verification(support_ratio=0.2),
            evidence_bundle=make_evidence(n=3),
            policy_config=self.config,
        )
        assert decision.decision == PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE
        assert "SUPPORT_BELOW_MINIMUM_THRESHOLD" in decision.reason_codes

    def test_high_risk_uses_stricter_threshold(self):
        # At risk_level=0.9, uses high_risk_support_ratio_override=0.95
        # A support ratio of 0.92 passes default (0.90) but fails high_risk (0.95)
        decision = self.engine.apply_policy(
            classification=make_classification(risk=0.9),
            verification_results=make_verification(support_ratio=0.92),
            evidence_bundle=make_evidence(n=3),
            policy_config=self.config,
        )
        assert decision.decision == PolicyDecisionType.ANSWER_QUALIFIED
