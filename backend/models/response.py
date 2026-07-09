from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID


@dataclass
class Citation:
    citation_id: UUID
    claim_id: UUID
    evidence_id: UUID
    source_name: str
    source_url: Optional[str]
    snippet: str
    trust_tier: int


@dataclass
class FinalResponse:
    query_id: UUID
    final_decision: str
    response_text: str
    confidence_summary: str
    citations: List[Citation] = field(default_factory=list)
    uncertainty_notes: List[str] = field(default_factory=list)
    refusal_reason: Optional[str] = None
    trace_id: Optional[UUID] = None
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "final_decision": self.final_decision,
            "response_text": self.response_text,
            "confidence_summary": self.confidence_summary,
            "citations": [
                {
                    "citation_id": c.citation_id,
                    "claim_id": c.claim_id,
                    "evidence_id": c.evidence_id,
                    "source_name": c.source_name,
                    "source_url": c.source_url,
                    "snippet": c.snippet,
                    "trust_tier": c.trust_tier,
                }
                for c in self.citations
            ],
            "uncertainty_notes": self.uncertainty_notes,
            "refusal_reason": self.refusal_reason,
            "trace_id": self.trace_id,
            "latency_ms": self.latency_ms,
        }
