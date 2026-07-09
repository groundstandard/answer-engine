"""
Integration test: full pipeline end-to-end with mocked LLM and retrieval.
Tests that the pipeline wires correctly and returns valid FinalResponse shapes.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from backend.orchestration.pipeline import PipelineController
from backend.models.policy import PolicyConfig


@pytest.fixture
def policy_config():
    return PolicyConfig(minimum_evidence_count=0)  # Relax for testing


@pytest.mark.asyncio
async def test_pipeline_returns_final_response_shape(policy_config):
    controller = PipelineController.__new__(PipelineController)

    mock_classification = MagicMock()
    mock_classification.classification_label = "FACTUAL"
    mock_classification.domain = "general"
    mock_classification.risk_level = 0.3

    from backend.models.evidence import EvidenceBundle
    mock_bundle = EvidenceBundle(
        query_id=uuid4(),
        evidence_items=[],
        retrieval_latency_ms=10,
        total_candidates_before_filter=0,
    )

    from backend.models.claims import ClaimSet
    mock_claim_set = ClaimSet(claims=[], total_count=0, critical_count=0)

    from backend.models.verification import VerificationResultSet
    mock_verification = VerificationResultSet(
        claim_results=[],
        aggregate_support_ratio=1.0,
        contains_contradiction=False,
        critical_claims_supported=True,
    )

    from backend.models.policy import PolicyDecision, PolicyDecisionType
    mock_policy = PolicyDecision(
        decision=PolicyDecisionType.ANSWER_VERIFIED,
        reason_codes=["FULL_SUPPORT_THRESHOLD_MET"],
        allowed_response_type="FULL",
        escalation_required=False,
        confidence_summary="All checks passed.",
    )

    from backend.models.response import FinalResponse
    mock_response = FinalResponse(
        query_id=uuid4(),
        final_decision="VERIFIED",
        response_text="Test response.",
        confidence_summary="All checks passed.",
    )

    controller.classifier = MagicMock()
    controller.classifier.classify_request = AsyncMock(return_value=mock_classification)
    controller.retriever = MagicMock()
    controller.retriever.retrieve_evidence = AsyncMock(return_value=mock_bundle)
    controller.claim_extractor = MagicMock()
    controller.claim_extractor.extract_claims = AsyncMock(return_value=mock_claim_set)
    controller.verifier = MagicMock()
    controller.verifier.verify_claims = AsyncMock(return_value=mock_verification)
    controller.policy_engine = MagicMock()
    controller.policy_engine.apply_policy = MagicMock(return_value=mock_policy)
    controller.composer = MagicMock()
    controller.composer.compose_response = AsyncMock(return_value=mock_response)
    controller.model_client = MagicMock()
    controller.model_client.call = AsyncMock(return_value={"draft_answer": "Test draft."})

    result = await controller.run_pipeline(
        query="What is the capital of France?",
        tenant_id=uuid4(),
        user_id=None,
        policy_config=policy_config,
    )

    assert result.final_decision in ("VERIFIED", "QUALIFIED", "REFUSED", "ESCALATED")
    assert isinstance(result.response_text, str)
    assert isinstance(result.latency_ms, int)
