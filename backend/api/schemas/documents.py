from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class DocumentIndexRequest(BaseModel):
    source_id: UUID
    tenant_id: UUID
    content_type: str = "text/plain"
    content: Optional[str] = None
    external_url: Optional[str] = None
    title: Optional[str] = None
    metadata: dict = {}


class DocumentIndexResponse(BaseModel):
    document_id: UUID
    indexing_status: str
    estimated_chunks: Optional[int] = None


class SourceCreate(BaseModel):
    tenant_id: UUID
    source_name: str
    source_type: str = "document"
    source_url: Optional[str] = None
    description: Optional[str] = None
    trust_tier: int = 3
    freshness_policy: str = "30d"


class SourceResponse(BaseModel):
    source_id: UUID
    source_name: str
    source_type: str
    trust_tier: int
    enabled: bool
    last_indexed_at: Optional[str] = None
