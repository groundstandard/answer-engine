"""Regression: the query trace (with UUIDs) must be JSON-serializable for logging."""
import json
from uuid import uuid4

from backend.models.response import FinalResponse, Citation


def test_final_response_trace_json_serializable():
    fr = FinalResponse(
        query_id=uuid4(),
        final_decision="VERIFIED",
        response_text="Paris.",
        confidence_summary="ok",
        citations=[Citation(
            citation_id=uuid4(), claim_id=uuid4(), evidence_id=uuid4(),
            source_name="Atlas", source_url=None, snippet="…", trust_tier=1,
        )],
        trace_id=uuid4(),
        latency_ms=5,
    )
    # save_query serializes with default=str; this must not raise on UUIDs.
    dumped = json.dumps({"final_response": fr.to_dict()}, default=str)
    assert "VERIFIED" in dumped
    assert "Atlas" in dumped
