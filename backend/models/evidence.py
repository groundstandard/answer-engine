from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID


@dataclass
class EvidenceItem:
    evidence_id: UUID
    source_id: UUID
    content: str
    source_name: str
    trust_score: float
    freshness_score: float
    trust_tier: int
    source_url: Optional[str] = None
    chunk_index: int = 0
    relevance_score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class EvidenceBundle:
    evidence_items: List[EvidenceItem]
    retrieval_latency_ms: int
    total_candidates_before_filter: int
    query_id: Optional[UUID] = None

    def to_prompt_string(self) -> str:
        parts = []
        for i, item in enumerate(self.evidence_items, 1):
            parts.append(
                f"[Source {i}] {item.source_name} (trust: {item.trust_score:.2f})\n{item.content}"
            )
        return "\n\n".join(parts)
