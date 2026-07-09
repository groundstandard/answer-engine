from uuid import uuid4
from backend.models.claims import ClaimSet, Claim, ClaimType


class ClaimExtractionService:
    def __init__(self, model_client):
        self.model_client = model_client

    async def extract_claims(self, draft_answer: str, query_context: str) -> ClaimSet:
        raw = await self.model_client.call(
            task_type="EXTRACT_CLAIMS",
            prompt_inputs={"draft_answer": draft_answer, "query_context": query_context},
            system_prompt=EXTRACT_SYSTEM_PROMPT,
        )
        claims = self._parse_claims(raw)
        return ClaimSet(
            claims=claims,
            total_count=len(claims),
            critical_count=sum(1 for c in claims if c.is_critical),
        )

    def _parse_claims(self, raw: dict) -> list[Claim]:
        raw_claims = raw.get("claims", [])
        if isinstance(raw_claims, str):
            return []
        claims = []
        for i, c in enumerate(raw_claims):
            if isinstance(c, str):
                text, is_critical = c, False
            else:
                text = c.get("text", c.get("claim", ""))
                is_critical = c.get("is_critical", False)
            if text:
                claims.append(
                    Claim(
                        claim_id=uuid4(),
                        claim_text=text,
                        claim_type=ClaimType.FACTUAL,
                        is_critical=is_critical,
                        importance_score=1.0 if is_critical else 0.5,
                    )
                )
        return claims


EXTRACT_SYSTEM_PROMPT = """Extract all verifiable factual claims from the draft answer.
Return JSON:
{
  "claims": [
    {"text": "...", "is_critical": true/false}
  ]
}
Mark a claim as critical if it is the central assertion that must be true for the answer to be correct.
Return valid JSON only."""
