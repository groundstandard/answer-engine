from uuid import UUID
from typing import List, Optional
from backend.config.settings import settings


class VectorStoreClient:
    """
    Unified interface for pgvector (local dev) and Qdrant (production).
    Switch via VECTOR_STORE_BACKEND env var.
    """

    def __init__(self):
        self.backend = settings.vector_store_backend

    async def upsert(
        self,
        collection: str,
        vectors: List[List[float]],
        payloads: List[dict],
        ids: List[str],
    ) -> None:
        if self.backend == "qdrant":
            await self._qdrant_upsert(collection, vectors, payloads, ids)
        else:
            await self._pgvector_upsert(collection, vectors, payloads, ids)

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 20,
        filter_payload: Optional[dict] = None,
    ) -> List[dict]:
        if self.backend == "qdrant":
            return await self._qdrant_search(collection, query_vector, top_k, filter_payload)
        return await self._pgvector_search(collection, query_vector, top_k, filter_payload)

    async def _qdrant_upsert(self, collection, vectors, payloads, ids):
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import PointStruct
        client = AsyncQdrantClient(url=settings.qdrant_url)
        points = [PointStruct(id=i, vector=v, payload=p) for i, v, p in zip(ids, vectors, payloads)]
        await client.upsert(collection_name=collection, points=points)

    async def _qdrant_search(self, collection, query_vector, top_k, filter_payload):
        from qdrant_client import AsyncQdrantClient
        client = AsyncQdrantClient(url=settings.qdrant_url)
        hits = await client.search(collection_name=collection, query_vector=query_vector, limit=top_k)
        return [{"id": h.id, "score": h.score, **h.payload} for h in hits]

    async def _pgvector_upsert(self, collection, vectors, payloads, ids):
        # Stub: production executes parameterized SQL INSERT
        pass

    async def _pgvector_search(self, collection, query_vector, top_k, filter_payload):
        # Stub: production executes cosine distance ORDER BY
        return []
