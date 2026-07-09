from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID


class QueryRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    tenant_id: UUID
    user_id: Optional[UUID] = None
    allowed_sources: Optional[List[UUID]] = None
    response_mode_preference: Optional[str] = "auto"
    domain_hint: Optional[str] = None
    include_trace: bool = False
    stream: bool = False


class Citation(BaseModel):
    citation_id: UUID
    claim_id: UUID
    evidence_id: UUID
    source_name: str
    source_url: Optional[str] = None
    snippet: str
    trust_tier: int


class QueryResponse(BaseModel):
    query_id: UUID
    final_decision: str
    response_text: str
    confidence_summary: str
    citations: List[Citation] = []
    uncertainty_notes: List[str] = []
    refusal_reason: Optional[str] = None
    trace_id: UUID
    latency_ms: int


class QueryTraceResponse(BaseModel):
    query_id: UUID
    query_text: str
    created_at: str
    classification: dict
    evidence_summary: dict
    claims: List[dict]
    policy_decision: dict
    final_response: dict
