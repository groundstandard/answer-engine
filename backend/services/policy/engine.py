from statistics import mean
from backend.models.classification import ClassificationResult
from backend.models.verification import VerificationResultSet, VerificationStatus
from backend.models.policy import PolicyConfig, PolicyDecision, PolicyDecisionType
from backend.models.evidence import EvidenceBundle


class PolicyEngine:
    """
    Deterministic rule-based policy engine.
    No model calls. No probabilistic decisions.
    Converts verification results into a binding PolicyDecision.
    """

    def apply_policy(
        self,
        classification: ClassificationResult,
        verification_results: VerificationResultSet,
        evidence_bundle: EvidenceBundle,
        policy_config: PolicyConfig,
    ) -> PolicyDecision:
        reason_codes = []

        # Gate 1: Evidence quantity
        if len(evidence_bundle.evidence_items) < policy_config.minimum_evidence_count:
            return self._refuse(
                reason_codes + ["INSUFFICIENT_EVIDENCE_COUNT"],
                PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            )

        # Gate 2: Source quality
        avg_trust = mean(e.trust_score for e in evidence_bundle.evidence_items)
        if avg_trust < policy_config.minimum_trust_score:
            return self._refuse(
                reason_codes + ["LOW_TRUST_EVIDENCE"],
                PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            )

        avg_freshness = mean(e.freshness_score for e in evidence_bundle.evidence_items)
        if avg_freshness < policy_config.minimum_freshness_score:
            return self._refuse(
                reason_codes + ["STALE_EVIDENCE"],
                PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            )

        # Gate 3: Critical claims
        if (
            policy_config.refusal_on_missing_critical_claim
            and not verification_results.critical_claims_supported
        ):
            return self._refuse(
                reason_codes + ["CRITICAL_CLAIM_UNSUPPORTED"],
                PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            )

        # Gate 4a: Cross-evidence conflict (sources disagree with each other).
        if getattr(verification_results, "cross_evidence_conflict", False):
            reason_codes.append("CROSS_EVIDENCE_CONFLICT")
            if policy_config.escalate_on_authoritative_conflict:
                return PolicyDecision(
                    decision=PolicyDecisionType.ESCALATE_HUMAN_REVIEW,
                    reason_codes=reason_codes + ["AUTHORITATIVE_SOURCE_CONFLICT"],
                    allowed_response_type="NONE",
                    escalation_required=True,
                    confidence_summary="Evidence sources contradict each other.",
                )
            return PolicyDecision(
                decision=PolicyDecisionType.ANSWER_QUALIFIED,
                reason_codes=reason_codes,
                allowed_response_type="PARTIAL",
                escalation_required=False,
                confidence_summary="Sources disagree; answer qualified.",
            )

        # Gate 4: Contradiction check
        contradicted = [
            r
            for r in verification_results.claim_results
            if r.status == VerificationStatus.CONTRADICTED
        ]
        if contradicted:
            contradiction_ratio = len(contradicted) / len(verification_results.claim_results)
            if contradiction_ratio > policy_config.max_contradicted_claim_ratio:
                reason_codes.append("CONTRADICTION_THRESHOLD_EXCEEDED")
                if policy_config.escalate_on_authoritative_conflict:
                    return PolicyDecision(
                        decision=PolicyDecisionType.ESCALATE_HUMAN_REVIEW,
                        reason_codes=reason_codes + ["AUTHORITATIVE_SOURCE_CONFLICT"],
                        allowed_response_type="NONE",
                        escalation_required=True,
                        confidence_summary="Authoritative sources in conflict.",
                    )
                return PolicyDecision(
                    decision=PolicyDecisionType.ANSWER_QUALIFIED,
                    reason_codes=reason_codes,
                    allowed_response_type="PARTIAL",
                    escalation_required=False,
                    confidence_summary="Some claims are contradicted by sources.",
                )

        # Gate 5: Support ratio
        support_ratio = verification_results.aggregate_support_ratio
        threshold = (
            policy_config.high_risk_support_ratio_override
            if classification.risk_level >= 0.7
            else policy_config.minimum_claim_support_ratio
        )

        if support_ratio >= threshold:
            reason_codes.append("FULL_SUPPORT_THRESHOLD_MET")
            return PolicyDecision(
                decision=PolicyDecisionType.ANSWER_VERIFIED,
                reason_codes=reason_codes,
                allowed_response_type="FULL",
                escalation_required=False,
                confidence_summary=f"Claim support: {support_ratio:.0%}. All thresholds met.",
            )
        elif support_ratio >= policy_config.qualified_claim_support_floor:
            reason_codes.append("PARTIAL_SUPPORT_THRESHOLD_MET")
            return PolicyDecision(
                decision=PolicyDecisionType.ANSWER_QUALIFIED,
                reason_codes=reason_codes,
                allowed_response_type="PARTIAL",
                escalation_required=False,
                confidence_summary=f"Claim support: {support_ratio:.0%}. Partial evidence only.",
            )
        else:
            return self._refuse(
                reason_codes + ["SUPPORT_BELOW_MINIMUM_THRESHOLD"],
                PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            )

    def _refuse(self, reason_codes: list, decision_type: PolicyDecisionType) -> PolicyDecision:
        return PolicyDecision(
            decision=decision_type,
            reason_codes=reason_codes,
            allowed_response_type="NONE",
            escalation_required=False,
            confidence_summary="Insufficient evidence to return a response.",
        )
