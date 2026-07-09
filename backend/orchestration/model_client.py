import json
import logging
from contextvars import ContextVar
from typing import Any, Optional

import httpx

from backend.config.settings import settings

logger = logging.getLogger(__name__)


_TASK_MODELS = {
    "CLASSIFY": settings.llm_model,
    "DRAFT": settings.llm_model,
    "EXTRACT_CLAIMS": settings.llm_model,
    "VERIFY": settings.llm_fallback_model,
    "COMPOSE": settings.llm_model,
    "RERANK": settings.llm_fallback_model,
}
# Ops can pin specialized models per task via settings.TASK_MODELS.
_TASK_MODELS.update(settings.TASK_MODELS or {})

# Per-request, per-tenant model overrides ({task_type: model_id}). Set by the
# request handler; read when resolving which model a task should use. Propagates
# into asyncio tasks (e.g. the verifier's gather) automatically.
MODEL_OVERRIDES: ContextVar[dict] = ContextVar("model_overrides", default={})


def resolve_model(task_type: str) -> str:
    overrides = MODEL_OVERRIDES.get() or {}
    return overrides.get(task_type) or _TASK_MODELS.get(task_type, settings.llm_model)


class ModelClient:
    """
    Calls the LLM for each pipeline task.

    Transport:
      - If N8N_LLM_WEBHOOK_URL is set, every call is POSTed to Bobby's n8n
        workflow (credentials live in n8n). This is the configured mode.
      - Otherwise it falls back to calling the Anthropic SDK directly, which
        keeps unit tests and local runs working without n8n.

    n8n webhook contract
    --------------------
    Request  (JSON body the Answer Engine sends):
        {
          "task_type":  "CLASSIFY|DRAFT|EXTRACT_CLAIMS|VERIFY|COMPOSE",
          "model":      "<suggested model id>",
          "system":     "<system prompt>",
          "prompt":     "<user message>",
          "temperature": 0.0,
          "max_tokens":  4096
        }
    Response (what the n8n "Respond to Webhook" node must return):
        { "text": "<the model's raw text output>" }
      (also accepted: {"output": "..."}, {"response": "..."},
       Anthropic-style {"content": [{"text": "..."}]}, or a bare string)

    The text is expected to be JSON matching each task's schema; it is parsed
    the same way regardless of transport.
    """

    def __init__(self):
        self._webhook_url = settings.N8N_LLM_WEBHOOK_URL.strip()
        # Build the Anthropic SDK client whenever a key is present — it serves as
        # the primary transport if there's no webhook, or the FALLBACK if the
        # n8n webhook fails.
        self._anthropic = None
        if settings.llm_api_key:
            import anthropic
            self._anthropic = anthropic.AsyncAnthropic(api_key=settings.llm_api_key)

    async def call(
        self,
        task_type: str,
        prompt_inputs: dict[str, Any],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        model = resolve_model(task_type)
        user_message = self._build_user_message(task_type, prompt_inputs)
        system = system_prompt or self._default_system(task_type)

        # Transport fallback chain: n8n webhook first (if configured), then the
        # Anthropic SDK (if a key is present). Each transport has its own retry.
        transports = []
        if self._webhook_url:
            transports.append(("n8n", lambda: self._call_n8n(
                task_type=task_type, model=model, system=system,
                prompt=user_message, temperature=temperature, max_tokens=max_tokens)))
        if self._anthropic:
            transports.append(("anthropic", lambda: self._call_anthropic(
                model=model, system=system, prompt=user_message,
                temperature=temperature, max_tokens=max_tokens)))

        if not transports:
            raise RuntimeError(
                "No LLM transport configured — set N8N_LLM_WEBHOOK_URL or LLM_API_KEY"
            )

        errors = []
        for name, fn in transports:
            try:
                raw_text = await fn()
                if errors:
                    logger.info("LLM call recovered via fallback transport '%s'", name)
                return self._parse_json_response(raw_text)
            except Exception as e:  # noqa: BLE001 — try the next transport in the chain
                errors.append(f"{name}: {e}")
                logger.warning("LLM transport '%s' failed: %s", name, e)

        # PRD 3.1: never a silent fallback to a fabricated answer.
        raise RuntimeError(f"All LLM transports failed: {'; '.join(errors)}")

    # ---- transports -------------------------------------------------------

    async def _call_n8n(self, task_type, model, system, prompt, temperature, max_tokens) -> str:
        payload = {
            "task_type": task_type,
            "model": model,
            "system": system,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {}
        if settings.N8N_WEBHOOK_AUTH_HEADER and settings.N8N_WEBHOOK_AUTH_TOKEN:
            headers[settings.N8N_WEBHOOK_AUTH_HEADER] = settings.N8N_WEBHOOK_AUTH_TOKEN

        last_error: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=settings.PIPELINE_TIMEOUT_SECONDS) as client:
            for attempt in range(1, settings.MAX_MODEL_RETRIES + 1):
                try:
                    resp = await client.post(self._webhook_url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return self._extract_text(resp)
                except Exception as e:  # noqa: BLE001 — retry transient webhook failures
                    last_error = e
                    logger.warning("n8n webhook attempt %s/%s failed: %s",
                                   attempt, settings.MAX_MODEL_RETRIES, e)
        # PRD 3.1: never a silent fallback — surface the failure.
        raise RuntimeError(f"n8n LLM webhook failed after retries: {last_error}")

    async def _call_anthropic(self, model, system, prompt, temperature, max_tokens) -> str:
        message = await self._anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text if message.content else ""

    @staticmethod
    def _extract_text(resp: httpx.Response) -> str:
        """Pull the model's text out of whatever shape n8n returns."""
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            return resp.text
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("text", "output", "response", "result", "answer"):
                if isinstance(data.get(key), str):
                    return data[key]
            content = data.get("content")
            if isinstance(content, list) and content and isinstance(content[0], dict):
                if isinstance(content[0].get("text"), str):
                    return content[0]["text"]
            return json.dumps(data)
        return str(data)

    # ---- prompt building (unchanged) --------------------------------------

    def _build_user_message(self, task_type: str, inputs: dict) -> str:
        if task_type == "CLASSIFY":
            return (
                f"Classify this query and return JSON:\n\nQuery: {inputs.get('query')}\n"
                f"Domain hint: {inputs.get('domain_hint', 'none')}"
            )
        if task_type == "DRAFT":
            return (
                f"Answer the query using ONLY the evidence provided. Return JSON with key 'draft_answer'.\n\n"
                f"Query: {inputs.get('query')}\n\nEvidence:\n{inputs.get('evidence_bundle')}"
            )
        if task_type == "EXTRACT_CLAIMS":
            return (
                f"Extract all factual claims from the draft. Return JSON with key 'claims' (list).\n\n"
                f"Draft: {inputs.get('draft_answer')}\n\nQuery context: {inputs.get('query_context')}"
            )
        if task_type == "VERIFY":
            return (
                f"Verify this claim against the evidence. Return JSON with keys: "
                f"status, confidence, explanation, supporting_snippet, supporting_source "
                f"(the N of the [Source N] passage that supports it).\n\n"
                f"Claim: {inputs.get('claim')}\n\nEvidence:\n{inputs.get('evidence')}"
            )
        if task_type == "COMPOSE":
            return (
                f"Compose the final response based on the decision and verified claims. "
                f"Return JSON with keys: response_text, uncertainty_notes.\n\n"
                f"Decision: {inputs.get('decision')}\n"
                f"Draft: {inputs.get('draft')}\n"
                f"Verified claims: {inputs.get('verified_claims')}"
            )
        if task_type == "RERANK":
            return (
                f"Rank the candidate passages by how well they answer the query. "
                f'Return JSON: {{"ranking": [source numbers, best first]}}.\n\n'
                f"Query: {inputs.get('query')}\n\nCandidates:\n{inputs.get('candidates')}"
            )
        return json.dumps(inputs)

    def _default_system(self, task_type: str) -> str:
        return (
            "You are a precise, evidence-focused AI assistant. "
            "Always respond with valid JSON matching the requested schema. "
            "Never hallucinate. If uncertain, express it explicitly."
        )

    def _parse_json_response(self, text: str) -> dict:
        text = text.strip()
        # Strip markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
