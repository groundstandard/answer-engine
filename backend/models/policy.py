from dataclasses import dataclass
from enum import Enum
from typing import List


class PolicyDecisionType(str, Enum):
    ANSWER_VERIFIED = "ANSWER_VERIFIED"
    ANSWER_QUALIFIED = "ANSWER_QUALIFIED"
    REFUSE_INSUFFICIENT_EVIDENCE = "REFUSE_INSUFFICIENT_EVIDENCE"
    REFUSE_UNVERIFIABLE = "REFUSE_UNVERIFIABLE"
    ESCALATE_HUMAN_REVIEW = "ESCALATE_HUMAN_REVIEW"


@dataclass
class PolicyConfig:
    minimum_evidence_count: int = 2
    minimum_trust_score: float = 0.6
    minimum_freshness_score: float = 0.5
    minimum_claim_support_ratio: float = 0.90
    qualified_claim_support_floor: float = 0.60
    max_contradicted_claim_ratio: float = 0.05
    require_exact_citation_for_high_risk: bool = True
    allow_inferred_support: bool = False
    refusal_on_missing_critical_claim: bool = True
    escalate_on_authoritative_conflict: bool = True
    high_risk_support_ratio_override: float = 0.95


@dataclass
class PolicyDecision:
    decision: PolicyDecisionType
    reason_codes: List[str]
    allowed_response_type: str
    escalation_required: bool
    confidence_summary: str
    policy_version: str = "1.0"
