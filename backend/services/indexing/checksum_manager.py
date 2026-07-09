import hashlib
from uuid import UUID


class ChecksumManager:
    def compute(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    async def already_indexed(self, checksum: str, tenant_id: UUID) -> bool:
        # Stub: production queries DB for existing checksum
        return False

    async def mark_indexed(self, checksum: str, source_id: UUID, tenant_id: UUID) -> None:
        # Stub: production inserts checksum record
        pass
