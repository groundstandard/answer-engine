from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID
from enum import Enum


class VerificationStatus(str, Enum):
    SUPPORTED_DIRECT = "SUPPORTED_DIRECT"
    SUPPORTED_PARAPHRASE = "SUPPORTED_PARAPHRASE"
    SUPPORTED_INFERRED = "SUPPORTED_INFERRED"
    WEAK_SUPPORT = "WEAK_SUPPORT"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass
class ClaimVerificationResult:
    claim_id: UUID
    status: VerificationStatus
    confidence: float
    supporting_evidence_ids: List[UUID] = field(default_factory=list)
    contradicting_evidence_ids: List[UUID] = field(default_factory=list)
    best_supporting_snippet: Optional[str] = None
    explanation: str = ""
    nli_scores: dict = field(default_factory=dict)


@dataclass
class VerificationResultSet:
    claim_results: List[ClaimVerificationResult]
    aggregate_support_ratio: float
    contains_contradiction: bool
    critical_claims_supported: bool
    verification_latency_ms: int = 0
