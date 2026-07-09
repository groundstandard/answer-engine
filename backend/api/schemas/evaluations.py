from pydantic import BaseModel
from typing import Optional, List, Any
from uuid import UUID


class FeedbackRequest(BaseModel):
    query_id: UUID
    rating: int
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    feedback_id: UUID
    status: str


class EvaluationRunRequest(BaseModel):
    tenant_id: UUID
    test_cases: List[dict]
    policy_profile: str = "default"


class EvaluationRunResponse(BaseModel):
    evaluation_id: UUID
    status: str
    total: int
    passed: int
    accuracy: float


class EvaluationResult(BaseModel):
    test_case_id: str
    query: str
    expected_decision: str
    actual_decision: str
    passed: bool
    latency_ms: int = 0
    error: Optional[str] = None
