from uuid import uuid4
from backend.models.policy import PolicyDecision, PolicyDecisionType
from backend.models.verification import VerificationResultSet, VerificationStatus
from backend.models.evidence import EvidenceBundle
from backend.models.response import FinalResponse, Citation


class ResponseComposer:
    def __init__(self, model_client):
        self.model_client = model_client

    async def compose_response(
        self,
        policy_decision: PolicyDecision,
        verification_results: VerificationResultSet,
        evidence_bundle: EvidenceBundle,
        original_query: str,
        draft_answer: str,
    ) -> FinalResponse:
        decision = policy_decision.decision

        if decision in (
            PolicyDecisionType.REFUSE_INSUFFICIENT_EVIDENCE,
            PolicyDecisionType.REFUSE_UNVERIFIABLE,
        ):
            return FinalResponse(
                query_id=uuid4(),
                final_decision="REFUSED",
                response_text=self._refusal_message(policy_decision),
                confidence_summary=policy_decision.confidence_summary,
                refusal_reason=", ".join(policy_decision.reason_codes),
            )

        if decision == PolicyDecisionType.ESCALATE_HUMAN_REVIEW:
            return FinalResponse(
                query_id=uuid4(),
                final_decision="ESCALATED",
                response_text="This query has been escalated for human review due to conflicting evidence.",
                confidence_summary=policy_decision.confidence_summary,
            )

        supported = [
            r for r in verification_results.claim_results
            if r.status in (
                VerificationStatus.SUPPORTED_DIRECT,
                VerificationStatus.SUPPORTED_PARAPHRASE,
                VerificationStatus.SUPPORTED_INFERRED,
            )
        ]

        raw = await self.model_client.call(
            task_type="COMPOSE",
            prompt_inputs={
                "decision": decision.value,
                "draft": draft_answer,
                "verified_claims": [r.explanation for r in supported],
            },
            system_prompt=COMPOSE_SYSTEM_PROMPT,
        )

        response_text = raw.get("response_text", draft_answer)
        uncertainty_notes = raw.get("uncertainty_notes", [])

        citations = self._build_citations(supported, evidence_bundle)

        return FinalResponse(
            query_id=uuid4(),
            final_decision=decision.value.replace("ANSWER_", ""),
            response_text=response_text,
            confidence_summary=policy_decision.confidence_summary,
            citations=citations,
            uncertainty_notes=uncertainty_notes,
        )

    def _refusal_message(self, decision: PolicyDecision) -> str:
        codes = decision.reason_codes
        if "NO_ANSWER_IN_EVIDENCE" in codes:
            return "I don't have a source that answers this question, so I can't provide a verified answer."
        if "UNVERIFIABLE_QUERY" in codes:
            return "This question can't be answered from verifiable evidence — it calls for a prediction, opinion, or fact no source can confirm."
        if "INSUFFICIENT_EVIDENCE_COUNT" in codes:
            return "I could not find enough reliable sources to answer this question."
        if "CRITICAL_CLAIM_UNSUPPORTED" in codes:
            return "The core claim in this answer could not be verified against available sources."
        if "STALE_EVIDENCE" in codes:
            return "The available sources are too outdated to provide a reliable answer."
        return "I cannot provide a verified answer to this question based on available evidence."

    def _build_citations(self, supported_results, evidence_bundle: EvidenceBundle) -> list[Citation]:
        citations = []
        evidence_map = {str(e.evidence_id): e for e in evidence_bundle.evidence_items}
        for result in supported_results:
            for eid in result.supporting_evidence_ids:
                evidence = evidence_map.get(str(eid))
                if evidence:
                    citations.append(
                        Citation(
                            citation_id=uuid4(),
                            claim_id=result.claim_id,
                            evidence_id=eid,
                            source_name=evidence.source_name,
                            source_url=evidence.source_url,
                            snippet=result.best_supporting_snippet or evidence.content[:200],
                            trust_tier=evidence.trust_tier,
                        )
                    )
        return citations


COMPOSE_SYSTEM_PROMPT = """Compose a final response using only verified evidence.
Return JSON:
{
  "response_text": "...",
  "uncertainty_notes": ["list of caveats or gaps, if any"]
}
Be accurate, factual, and cite only what was verified. Return valid JSON only."""
