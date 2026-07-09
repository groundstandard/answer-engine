from dataclasses import dataclass
from typing import Optional


@dataclass
class ClassificationResult:
    classification_label: str
    domain: str
    risk_level: float
    requires_evidence: bool
    complexity_score: float
    raw_label: str
    retrieval_query_hint: Optional[str] = None
