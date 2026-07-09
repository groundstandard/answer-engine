import logging
from typing import List

import httpx

from backend.services.indexing.chunker import Chunk
from backend.config.settings import settings

logger = logging.getLogger(__name__)


class Embedder:
    """
    Generates vector embeddings.

    Transport:
      - If N8N_EMBEDDING_WEBHOOK_URL is set, texts are POSTed to Bobby's n8n
        embedding workflow (credentials live in n8n).
      - Otherwise it falls back to calling OpenAI directly.

    n8n embedding webhook contract
    ------------------------------
    Request:  { "input": ["text 1", "text 2", ...] }
    Response: { "embeddings": [[...1536 floats...], [...], ...] }

    The workflow MUST use the same embedding model as indexing and query time
    (text-embedding-3-small, 1536 dims) so vectors stay comparable.
    """

    def __init__(self):
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        self._webhook_url = settings.N8N_EMBEDDING_WEBHOOK_URL.strip()
        self._use_n8n = bool(self._webhook_url)
        self._openai = None
        if not self._use_n8n:
            import openai
            self._openai = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed(self, chunks: List[Chunk]) -> List[List[float]]:
        if not chunks:
            return []
        return await self._embed_texts([c.text for c in chunks])

    async def embed_query(self, query: str) -> List[float]:
        vectors = await self._embed_texts([query])
        return vectors[0]

    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if self._use_n8n:
            return await self._embed_via_n8n(texts)
        response = await self._openai.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in response.data]

    async def _embed_via_n8n(self, texts: List[str]) -> List[List[float]]:
        headers = {}
        if settings.N8N_WEBHOOK_AUTH_HEADER and settings.N8N_WEBHOOK_AUTH_TOKEN:
            headers[settings.N8N_WEBHOOK_AUTH_HEADER] = settings.N8N_WEBHOOK_AUTH_TOKEN

        last_error = None
        async with httpx.AsyncClient(timeout=settings.PIPELINE_TIMEOUT_SECONDS) as client:
            for attempt in range(1, settings.MAX_MODEL_RETRIES + 1):
                try:
                    resp = await client.post(self._webhook_url, json={"input": texts}, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    embeddings = data.get("embeddings") if isinstance(data, dict) else data
                    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
                        raise ValueError("n8n embedding response shape invalid")
                    return embeddings
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    logger.warning("n8n embedding attempt %s/%s failed: %s",
                                   attempt, settings.MAX_MODEL_RETRIES, e)
        raise RuntimeError(f"n8n embedding webhook failed after retries: {last_error}")
