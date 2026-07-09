import logging
from uuid import UUID
from typing import Optional

logger = logging.getLogger(__name__)


class DocumentIndexingService:
    """Parses, chunks, embeds, and stores documents for retrieval."""

    def __init__(self):
        from backend.services.indexing.chunker import Chunker
        from backend.services.indexing.embedder import Embedder
        from backend.services.indexing.vector_writer import VectorWriter
        from backend.services.indexing.checksum_manager import ChecksumManager

        self.chunker = Chunker()
        self.embedder = Embedder()
        self.vector_writer = VectorWriter()
        self.checksum_manager = ChecksumManager()

    async def index_document(
        self,
        content: str,
        source_id: UUID,
        tenant_id: UUID,
        mime_type: str = "text/plain",
        metadata: Optional[dict] = None,
    ) -> dict:
        checksum = self.checksum_manager.compute(content)
        if await self.checksum_manager.already_indexed(checksum, tenant_id):
            return {"status": "already_indexed", "checksum": checksum}

        chunks = self.chunker.chunk(content, metadata=metadata or {})

        # Embeddings are best-effort: if the embedding provider is unavailable,
        # still store the chunks (embedding = null) so keyword/BM25 search works.
        embedded = False
        try:
            embeddings = await self.embedder.embed(chunks)
            embedded = True
        except Exception as e:  # noqa: BLE001
            logger.warning("Embeddings unavailable — indexing for keyword search only: %s", e)
            embeddings = [None] * len(chunks)

        await self.vector_writer.write(
            chunks=chunks,
            embeddings=embeddings,
            source_id=source_id,
            tenant_id=tenant_id,
        )
        await self.checksum_manager.mark_indexed(checksum, source_id, tenant_id)

        return {
            "status": "indexed",
            "chunks": len(chunks),
            "checksum": checksum,
            "embedded": embedded,
        }
