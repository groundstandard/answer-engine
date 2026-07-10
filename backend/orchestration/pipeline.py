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
        from backend.services.verification.contradiction_checker import ContradictionChecker
        from backend.services.policy.engine import PolicyEngine
        from backend.services.composition.composer import ResponseComposer
        from backend.orchestration.model_client import ModelClient

        self.model_client = ModelClient()
        self.classifier = ClassificationService(self.model_client)
        self.retriever = RetrievalService()
        self.claim_extractor = ClaimExtractionService(self.model_client)
        self.verifier = ClaimVerificationService(self.model_client)
        self.contradiction_checker = ContradictionChecker(self.model_client)
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
        on_event=None,
    ) -> FinalResponse:
        pipeline_start = time.monotonic()
        trace_id = uuid4()

        # Stage 1: Classification
        classification = await self.classifier.classify_request(
            query=query,
            domain_hint=domain_hint,
            policy_config=policy_config,
        )
        await self._emit(on_event, "classification", {
            "label": classification.classification_label,
            "risk_level": getattr(classification, "risk_level", None),
            "domain": getattr(classification, "domain", None),
        })

        # Cost routing: cheaper model for low-risk generation tasks.
        self._apply_cost_routing(classification)

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
        await self._emit(on_event, "retrieval", {
            "evidence_count": len(evidence_bundle.evidence_items),
        })

        # Stage 3: Draft + Claim Extraction
        draft_answer, claim_set = await self._generate_draft_and_claims(
            query=query,
            evidence_bundle=evidence_bundle,
            classification=classification,
        )
        await self._emit(on_event, "claims", {"claim_count": claim_set.total_count})

        # Stage 4: Claim Verification
        verification_results = await self.verifier.verify_claims(
            claim_set=claim_set,
            evidence_bundle=evidence_bundle,
            policy_config=policy_config,
        )
        await self._emit(on_event, "verification", {
            "support_ratio": verification_results.aggregate_support_ratio,
            "claims": [
                {"claim_id": str(r.claim_id), "status": r.status.value}
                for r in verification_results.claim_results
            ],
        })

        # Stage 4b: Cross-evidence contradiction pass (optional, one LLM call).
        if settings.ENABLE_CONTRADICTION_CHECK:
            conflict, explanation = await self.contradiction_checker.check(
                query=query, evidence_bundle=evidence_bundle,
            )
            if conflict:
                verification_results.cross_evidence_conflict = True
                verification_results.conflict_explanation = explanation
                verification_results.contains_contradiction = True
            await self._emit(on_event, "contradiction", {"conflict": conflict})

        # Stage 5: Policy Decision
        policy_decision = self.policy_engine.apply_policy(
            classification=classification,
            verification_results=verification_results,
            evidence_bundle=evidence_bundle,
            policy_config=policy_config,
        )
        await self._emit(on_event, "policy", {"decision": policy_decision.decision.value})

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

    @staticmethod
    async def _emit(on_event, stage: str, data: dict) -> None:
        if on_event is not None:
            await on_event(stage, data)

    def _apply_cost_routing(self, classification) -> None:
        """Route generation tasks to the cheaper model when the query is low-risk.
        Respects any explicit per-tenant model override already in effect."""
        if not settings.ENABLE_COST_ROUTING:
            return
        risk = getattr(classification, "risk_level", 1.0)
        if risk is None or risk > settings.COST_ROUTING_RISK_THRESHOLD:
            return
        from backend.orchestration.model_client import MODEL_OVERRIDES
        current = dict(MODEL_OVERRIDES.get() or {})
        for task in ("DRAFT", "EXTRACT_CLAIMS", "COMPOSE"):
            current.setdefault(task, settings.llm_fallback_model)
        MODEL_OVERRIDES.set(current)

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
