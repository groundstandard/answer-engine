import time
from uuid import uuid4, UUID
from typing import Optional, List
from backend.models.response import FinalResponse
from backend.models.policy import PolicyConfig
from backend.config.settings import settings


class PipelineController:
    """
    Orchestrates the full evidence-gated pipeline.
    Stage order is enforced — no stage may be skipped.
    """

    def __init__(self):
        # Services are imported lazily to avoid circular imports
        from backend.services.classification.classifier import ClassificationService
        from backend.services.retrieval.retriever import RetrievalService
        from backend.services.claims.extractor import ClaimExtractionService
        from backend.services.verification.verifier import ClaimVerificationService
        from backend.services.policy.engine import PolicyEngine
        from backend.services.composition.composer import ResponseComposer
        from backend.orchestration.model_client import ModelClient

        self.model_client = ModelClient()
        self.classifier = ClassificationService(self.model_client)
        self.retriever = RetrievalService()
        self.claim_extractor = ClaimExtractionService(self.model_client)
        self.verifier = ClaimVerificationService(self.model_client)
        self.policy_engine = PolicyEngine()
        self.composer = ResponseComposer(self.model_client)

    async def run_pipeline(
        self,
        query: str,
        tenant_id: UUID,
        user_id: Optional[UUID],
        policy_config: PolicyConfig,
        source_scope: Optional[List[UUID]] = None,
        domain_hint: Optional[str] = None,
    ) -> FinalResponse:
        pipeline_start = time.monotonic()
        trace_id = uuid4()

        # Stage 1: Classification
        classification = await self.classifier.classify_request(
            query=query,
            domain_hint=domain_hint,
            policy_config=policy_config,
        )

        # Short-circuit for non-factual queries
        if classification.classification_label in ("CREATIVE", "UNVERIFIABLE"):
            return FinalResponse(
                query_id=uuid4(),
                final_decision="QUALIFIED",
                response_text="This query does not require evidence verification.",
                confidence_summary="Non-factual query — verification skipped.",
                uncertainty_notes=["Response is not evidence-verified."],
                trace_id=trace_id,
                latency_ms=int((time.monotonic() - pipeline_start) * 1000),
            )

        # Stage 2: Retrieval
        evidence_bundle = await self.retriever.retrieve_evidence(
            query=query,
            classification=classification,
            source_scope=source_scope,
            tenant_id=tenant_id,
        )

        # Stage 3: Draft + Claim Extraction
        draft_answer, claim_set = await self._generate_draft_and_claims(
            query=query,
            evidence_bundle=evidence_bundle,
            classification=classification,
        )

        # Stage 4: Claim Verification
        verification_results = await self.verifier.verify_claims(
            claim_set=claim_set,
            evidence_bundle=evidence_bundle,
            policy_config=policy_config,
        )

        # Stage 5: Policy Decision
        policy_decision = self.policy_engine.apply_policy(
            classification=classification,
            verification_results=verification_results,
            evidence_bundle=evidence_bundle,
            policy_config=policy_config,
        )

        # Stage 6: Response Composition
        final_response = await self.composer.compose_response(
            policy_decision=policy_decision,
            verification_results=verification_results,
            evidence_bundle=evidence_bundle,
            original_query=query,
            draft_answer=draft_answer,
        )

        final_response.latency_ms = int((time.monotonic() - pipeline_start) * 1000)
        final_response.trace_id = trace_id
        return final_response

    async def _generate_draft_and_claims(self, query, evidence_bundle, classification):
        raw = await self.model_client.call(
            task_type="DRAFT",
            prompt_inputs={
                "query": query,
                "evidence_bundle": evidence_bundle.to_prompt_string(),
                "domain": classification.domain,
            },
        )
        draft = raw.get("draft_answer", "")
        claim_set = await self.claim_extractor.extract_claims(
            draft_answer=draft,
            query_context=query,
        )
        return draft, claim_set
