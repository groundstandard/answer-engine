from backend.models.classification import ClassificationResult
from backend.models.policy import PolicyConfig


class ClassificationService:
    def __init__(self, model_client):
        self.model_client = model_client

    async def classify_request(
        self,
        query: str,
        policy_config: PolicyConfig,
        domain_hint: str | None = None,
    ) -> ClassificationResult:
        raw = await self.model_client.call(
            task_type="CLASSIFY",
            prompt_inputs={"query": query, "domain_hint": domain_hint},
            system_prompt=CLASSIFY_SYSTEM_PROMPT,
        )
        return self._parse(raw, query)

    def _parse(self, raw: dict, query: str) -> ClassificationResult:
        return ClassificationResult(
            classification_label=raw.get("classification_label", "FACTUAL"),
            domain=raw.get("domain", "general"),
            risk_level=float(raw.get("risk_level", 0.5)),
            requires_evidence=raw.get("requires_evidence", True),
            complexity_score=float(raw.get("complexity_score", 0.5)),
            raw_label=raw.get("classification_label", "FACTUAL"),
        )


CLASSIFY_SYSTEM_PROMPT = """You are a query classification engine.
Classify the query and return JSON with these fields:
- classification_label: one of FACTUAL, PROCEDURAL, COMPARATIVE, CREATIVE, UNVERIFIABLE
- domain: e.g. "medical", "legal", "finance", "general"
- risk_level: float 0.0-1.0 (higher = higher stakes)
- requires_evidence: boolean
- complexity_score: float 0.0-1.0

Respond with valid JSON only."""
