from typing import List
from backend.models.evidence import EvidenceItem
from backend.config.settings import settings


class TrustFilter:
    """Removes evidence items below the minimum trust threshold."""

    def filter(self, items: List[EvidenceItem], min_trust: float = 0.4) -> List[EvidenceItem]:
        return [e for e in items if e.trust_score >= min_trust]
