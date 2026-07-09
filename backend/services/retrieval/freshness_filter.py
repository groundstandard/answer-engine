from typing import List
from backend.models.evidence import EvidenceItem


class FreshnessFilter:
    """Removes evidence items below the minimum freshness threshold."""

    def filter(self, items: List[EvidenceItem], min_freshness: float = 0.3) -> List[EvidenceItem]:
        return [e for e in items if e.freshness_score >= min_freshness]
