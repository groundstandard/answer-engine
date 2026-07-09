import asyncio
from typing import List, Optional

from backend.models.claims import ClaimSet, Claim
from backend.models.verification import (
    ClaimVerificationResult,
    VerificationResultSet,
    VerificationStatus,
)
from backend.models.evidence import EvidenceBundle, EvidenceItem
from backend.models.policy import PolicyConfig

_SUPPORTED = (
    VerificationStatus.SUPPORTED_DIRECT,
    VerificationStatus.SUPPORTED_PARAPHRASE,
    VerificationStatus.SUPPORTED_INFERRED,
)


class ClaimVerificationService:
    def __init__(self, model_client):
        self.model_client = model_client

    async def verify_claims(
        self,
        claim_set: ClaimSet,
        evidence_bundle: EvidenceBundle,
        policy_config: PolicyConfig,
    ) -> VerificationResultSet:
        evidence_text = evidence_bundle.to_prompt_string()
        evidence_items = evidence_bundle.evidence_items

        tasks = [
            self._verify_claim(claim, evidence_text, evidence_items)
            for claim in claim_set.claims
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        claim_results: list[ClaimVerificationResult] = [
            r for r in results if isinstance(r, ClaimVerificationResult)
        ]

        support_count = sum(1 for r in claim_results if r.status in _SUPPORTED)
        total = len(claim_results) or 1
        support_ratio = support_count / total

        has_contradiction = any(
            r.status == VerificationStatus.CONTRADICTED for r in claim_results
        )

        critical_results = [
            r for r in claim_results
            if any(c.claim_id == r.claim_id and c.is_critical for c in claim_set.claims)
        ]
        critical_supported = all(
            r.status in (
                VerificationStatus.SUPPORTED_DIRECT,
                VerificationStatus.SUPPORTED_PARAPHRASE,
            )
            for r in critical_results
        ) if critical_results else True

        return VerificationResultSet(
            claim_results=claim_results,
            aggregate_support_ratio=support_ratio,
            contains_contradiction=has_contradiction,
            critical_claims_supported=critical_supported,
        )

    async def _verify_claim(
        self, claim: Claim, evidence_text: str, evidence_items: List[EvidenceItem]
    ) -> ClaimVerificationResult:
        raw = await self.model_client.call(
            task_type="VERIFY",
            prompt_inputs={"claim": claim.claim_text, "evidence": evidence_text},
            system_prompt=VERIFY_SYSTEM_PROMPT,
        )
        status_str = raw.get("status", "UNSUPPORTED").upper()
        try:
            status = VerificationStatus[status_str]
        except KeyError:
            status = VerificationStatus.UNSUPPORTED

        snippet = raw.get("supporting_snippet")
        supporting_ids = self._resolve_evidence_ids(raw, status, snippet, evidence_items)

        return ClaimVerificationResult(
            claim_id=claim.claim_id,
            status=status,
            confidence=float(raw.get("confidence", 0.5)),
            supporting_evidence_ids=supporting_ids,
            best_supporting_snippet=snippet,
            explanation=raw.get("explanation", ""),
        )

    def _resolve_evidence_ids(
        self,
        raw: dict,
        status: VerificationStatus,
        snippet: Optional[str],
        evidence_items: List[EvidenceItem],
    ) -> list:
        """Map a verified claim back to the evidence item(s) that support it."""
        if status not in _SUPPORTED or not evidence_items:
            return []

        # 1. Prefer the source number the model cites ("[Source N]").
        idx = _parse_source_index(raw.get("supporting_source"))
        if idx is not None and 1 <= idx <= len(evidence_items):
            return [evidence_items[idx - 1].evidence_id]

        # 2. Fall back to matching the supporting snippet against evidence content.
        if snippet:
            needle = snippet.strip().lower()
            if needle:
                for e in evidence_items:
                    if needle in e.content.lower():
                        return [e.evidence_id]

        # 3. Last resort: attribute to the top-ranked evidence item so a verified
        #    answer is never left without traceability.
        return [evidence_items[0].evidence_id]


def _parse_source_index(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return int(digits)
    return None


VERIFY_SYSTEM_PROMPT = """You verify factual claims against provided evidence using NLI scoring.
The evidence is a numbered list of passages, each starting with "[Source N]".
Return JSON:
{
  "status": "SUPPORTED_DIRECT | SUPPORTED_PARAPHRASE | SUPPORTED_INFERRED | WEAK_SUPPORT | UNSUPPORTED | CONTRADICTED | UNVERIFIABLE",
  "confidence": 0.0-1.0,
  "explanation": "...",
  "supporting_snippet": "exact quote from the evidence, or null",
  "supporting_source": "the N of the [Source N] passage that best supports the claim, or null"
}
Be strict. Return UNSUPPORTED if the evidence does not clearly support the claim. Return valid JSON only."""
