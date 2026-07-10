"""Cross-evidence contradiction pass (PRD Section 12: contradiction-aware verification).

Per-claim NLI already flags claims that a passage contradicts. This adds the
missing "multi-hop" angle: do two or more *evidence passages* disagree with each
other on the question? A VERIFIED answer built on internally-conflicting sources
is exactly what the evidence gate is meant to catch, so when a conflict is found
among trusted sources the pipeline downgrades / escalates the decision.

Runs a single LLM call and is gated by settings.ENABLE_CONTRADICTION_CHECK so it
adds no latency unless explicitly turned on.
"""

from typing import Optional

from backend.models.evidence import EvidenceBundle


class ContradictionChecker:
    def __init__(self, model_client):
        self.model_client = model_client

    async def check(
        self, query: str, evidence_bundle: EvidenceBundle
    ) -> tuple[bool, Optional[str]]:
        items = evidence_bundle.evidence_items
        if len(items) < 2:
            return False, None

        raw = await self.model_client.call(
            task_type="VERIFY",
            prompt_inputs={
                "query": query,
                "evidence": evidence_bundle.to_prompt_string(),
            },
            system_prompt=CONTRADICTION_SYSTEM_PROMPT,
        )
        found = bool(raw.get("contradiction_found", False))
        explanation = raw.get("explanation") if found else None
        return found, explanation


CONTRADICTION_SYSTEM_PROMPT = """You compare numbered evidence passages ("[Source N]") to each other.
Decide whether two or more passages DIRECTLY CONTRADICT one another on facts relevant to the user's question.
Differences in wording, scope, or detail are NOT contradictions — only mutually exclusive factual claims are.
Return JSON only:
{
  "contradiction_found": true | false,
  "conflicting_sources": [N, M],
  "explanation": "one sentence naming the conflicting facts, or empty"
}"""
