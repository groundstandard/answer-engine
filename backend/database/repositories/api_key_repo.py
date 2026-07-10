import hashlib
import secrets
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> str:
    return "ae_" + secrets.token_urlsafe(32)


class ApiKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant_id: UUID, role: str, name: Optional[str]) -> tuple[UUID, str]:
        """Create a key; returns (id, PLAINTEXT key). Only the hash is stored."""
        raw = generate_key()
        key_id = uuid4()
        await self.db.execute(
            text("""
                INSERT INTO api_keys (id, tenant_id, key_hash, role, name)
                VALUES (:id, :tenant_id, :key_hash, :role, :name)
            """),
            {
                "id": str(key_id), "tenant_id": str(tenant_id),
                "key_hash": hash_key(raw), "role": role, "name": name,
            },
        )
        await self.db.commit()
        return key_id, raw

    async def verify(self, raw_key: str) -> Optional[dict]:
        """Resolve an active key to {tenant_id, role}, or None if invalid."""
        result = await self.db.execute(
            text("""
                SELECT tenant_id, role FROM api_keys
                WHERE key_hash = :h AND is_active = TRUE
            """),
            {"h": hash_key(raw_key)},
        )
        row = result.fetchone()
        if not row:
            return None
        # Best-effort last-used stamp (ignore failures).
        try:
            await self.db.execute(
                text("UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = :h"),
                {"h": hash_key(raw_key)},
            )
            await self.db.commit()
        except Exception:  # noqa: BLE001
            await self.db.rollback()
        return {"tenant_id": str(row[0]), "role": row[1]}
