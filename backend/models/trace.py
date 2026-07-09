from dataclasses import dataclass, field
from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime


@dataclass
class StageTrace:
    stage_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    latency_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineTrace:
    trace_id: UUID
    query_id: UUID
    tenant_id: UUID
    query_text: str
    stages: List[StageTrace] = field(default_factory=list)
    total_latency_ms: int = 0
    final_decision: Optional[str] = None
    model_calls: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def add_stage(self, stage: StageTrace) -> None:
        self.stages.append(stage)

    def to_dict(self) -> dict:
        return {
            "trace_id": str(self.trace_id),
            "query_id": str(self.query_id),
            "tenant_id": str(self.tenant_id),
            "stages": [
                {
                    "stage": s.stage_name,
                    "latency_ms": s.latency_ms,
                    "success": s.success,
                    "error": s.error,
                }
                for s in self.stages
            ],
            "total_latency_ms": self.total_latency_ms,
            "final_decision": self.final_decision,
            "model_calls": self.model_calls,
            "tokens_used": self.tokens_used,
        }
