import time
from uuid import uuid4, UUID
from typing import Optional, List
from backend.models.response import FinalResponse
from backend.models.policy import PolicyConfig, PolicyDecision, PolicyDecisionType
from backend.config.settings import settings

# When the model's own draft declines to answer from the evidence, the answer is
# a non-answer — it must be gated as REFUSED, never VERIFIED. These markers catch
# that abstention so a "the evidence doesn't cover this" reply can't be labeled
# as a verified answer (the audit-trail failure Bobby flagged).
_ABSTENTION_MARKERS = (
    "does not contain", "do not contain",
    "does not include any information", "not include any information",
    "does not mention", "does not address", "does not specify",
    "does not provide information", "do not provide information",
    "no information regarding", "no information about", "no information on",
    "could not find", "cannot find", "can't find",
    "unable to answer", "cannot answer", "can't answer",
    "no relevant evidence", "not enough information", "insufficient information",
    "evidence provided does not", "evidence does not", "no evidence",
)

# When the answer itself says the result depends on unspecified jurisdiction or
# varies by state, a flat VERIFIED overstates confidence — it should be QUALIFIED
# so the caveat is surfaced (Bobby's jurisdiction-ambiguity category).
_CONTEXT_DEPENDENT_MARKERS = (
    "varies by state", "varies by jurisdiction", "vary by state", "vary by jurisdiction",
    "depends on the jurisdiction", "depends on the state", "depends on your state",
    "depending on the state", "depending on the jurisdiction", "depending on your",
    "differs by state", "differ by state", "state-by-state", "state by state",
    "some states", "other states", "one-party consent", "two-party consent",
    "all-party consent",
)


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

        # Unverifiable queries (predictions, opinions, unknowable facts) can never
        # be evidence-backed — refuse, don't qualify. This is what a legal/medical
        # buyer expects: no answer to "will the Supreme Court…" or "which judge is…".
        if classification.classification_label == "UNVERIFIABLE":
            return FinalResponse(
                query_id=uuid4(),
                final_decision="REFUSED",
                response_text="This question can't be answered from verifiable evidence — it calls for a prediction, opinion, or fact no source can confirm.",
                confidence_summary="Unverifiable query — no evidence-based answer possible.",
                refusal_reason="UNVERIFIABLE_QUERY",
                uncertainty_notes=["Not answerable from evidence."],
                trace_id=trace_id,
                latency_ms=int((time.monotonic() - pipeline_start) * 1000),
            )
        # Creative/non-factual requests simply don't need verification.
        if classification.classification_label == "CREATIVE":
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

        # Abstention guard: if the drafted answer itself declines to answer from
        # the evidence (e.g. "the evidence does not contain information on this
        # case"), that is NOT a verified answer — force a refusal. Fixes the
        # fabricated-case bait and "no info but marked VERIFIED" failures.
        if (
            policy_decision.decision in (
                PolicyDecisionType.ANSWER_VERIFIED,
                PolicyDecisionType.ANSWER_QUALIFIED,
            )
            and self._is_abstention(draft_answer)
        ):
            policy_decision = PolicyDecision(
                decision=PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
                reason_codes=(policy_decision.reason_codes or []) + ["NO_ANSWER_IN_EVIDENCE"],
                allowed_response_type="NONE",
                escalation_required=False,
                confidence_summary="The evidence does not answer the question.",
            )
        # Jurisdiction/context guard: a verified answer that itself says the result
        # varies by state / depends on jurisdiction is context-dependent — qualify it.
        elif (
            policy_decision.decision == PolicyDecisionType.ANSWER_VERIFIED
            and self._depends_on_context(draft_answer)
        ):
            policy_decision = PolicyDecision(
                decision=PolicyDecisionType.ANSWER_QUALIFIED,
                reason_codes=(policy_decision.reason_codes or []) + ["CONTEXT_DEPENDENT"],
                allowed_response_type="PARTIAL",
                escalation_required=False,
                confidence_summary="Answer depends on jurisdiction or context not specified in the question.",
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

    @staticmethod
    def _is_abstention(draft_answer) -> bool:
        """True when the drafted answer declines to answer from the evidence.
        The draft may arrive as a str or a structured dict/list, so coerce first."""
        if not draft_answer:
            return True
        text = (draft_answer if isinstance(draft_answer, str) else str(draft_answer)).lower()
        return any(marker in text for marker in _ABSTENTION_MARKERS)

    @staticmethod
    def _depends_on_context(draft_answer) -> bool:
        """True when the answer itself says the result varies by jurisdiction/state."""
        if not draft_answer:
            return False
        text = (draft_answer if isinstance(draft_answer, str) else str(draft_answer)).lower()
        return any(marker in text for marker in _CONTEXT_DEPENDENT_MARKERS)

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
