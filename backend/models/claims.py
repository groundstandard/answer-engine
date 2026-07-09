from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID
from enum import Enum


class ClaimType(str, Enum):
    FACTUAL = "factual"
    STATISTICAL = "statistical"
    CAUSAL = "causal"
    TEMPORAL = "temporal"
    DEFINITIONAL = "definitional"


@dataclass
class Claim:
    claim_id: UUID
    claim_text: str
    claim_type: ClaimType
    is_critical: bool = False
    importance_score: float = 0.5
    normalized_claim: Optional[str] = None


@dataclass
class ClaimSet:
    claims: List[Claim]
    total_count: int
    critical_count: int
    extraction_latency_ms: int = 0
