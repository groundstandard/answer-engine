import base64
import hashlib
import secrets
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from backend.config.settings import settings


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> str:
    return "ae_" + secrets.token_urlsafe(32)


def _fernet():
    from cryptography.fernet import Fernet
    secret = (settings.KEY_ENCRYPTION_SECRET or settings.JWT_SECRET or "changeme").encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def encrypt_key(raw: str) -> str:
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_key(cipher: Optional[str]) -> Optional[str]:
    """Recover a stored key. Returns None if absent or undecryptable (e.g. secret rotated)."""
    if not cipher:
        return None
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except Exception:  # noqa: BLE001 — never leak crypto errors to callers
        return None


def mask_key(raw: Optional[str]) -> Optional[str]:
    """ae_GXYKYS…AdrY — enough to recognize a key, not enough to use it."""
    if not raw:
        return None
    body = raw[3:] if raw.startswith("ae_") else raw
    if len(body) <= 8:
        return "ae_…"
    return f"ae_{body[:4]}…{body[-4:]}"


class ApiKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, tenant_id: UUID, role: str, name: Optional[str],
        expires_in_days: Optional[int] = None,
    ) -> tuple[UUID, str]:
        """Create a key; returns (id, PLAINTEXT key). Only the hash is stored.
        expires_in_days=None → never expires (e.g. the owner's key)."""
        raw = generate_key()
        key_id = uuid4()
        await self.db.execute(
            text("""
                INSERT INTO api_keys (id, tenant_id, key_hash, key_cipher, role, name, expires_at)
                VALUES (:id, :tenant_id, :key_hash, :key_cipher, :role, :name,
                        CASE WHEN CAST(:days AS INT) IS NULL THEN NULL
                             ELSE NOW() + CAST(:days AS INT) * INTERVAL '1 day' END)
            """),
            {
                "id": str(key_id), "tenant_id": str(tenant_id),
                "key_hash": hash_key(raw), "key_cipher": encrypt_key(raw),
                "role": role, "name": name, "days": expires_in_days,
            },
        )
        await self.db.commit()
        return key_id, raw

    async def list_for_tenant(self, tenant_id: UUID) -> list[dict]:
        """List key metadata for a tenant (never the key/hash), newest first."""
        result = await self.db.execute(
            text("""
                SELECT id, name, role, is_active, created_at, last_used_at, expires_at, key_cipher
                FROM api_keys WHERE tenant_id = :tid
                ORDER BY created_at DESC
            """),
            {"tid": str(tenant_id)},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def revoke(self, key_id: UUID, tenant_id: UUID) -> bool:
        """Deactivate a key (immediate). Returns True if a key was revoked."""
        result = await self.db.execute(
            text("""
                UPDATE api_keys SET is_active = FALSE
                WHERE id = :id AND tenant_id = :tid AND is_active = TRUE
            """),
            {"id": str(key_id), "tid": str(tenant_id)},
        )
        await self.db.commit()
        return result.rowcount > 0

    async def verify(self, raw_key: str) -> Optional[dict]:
        """Resolve an active, non-expired key to {tenant_id, role}, or None."""
        result = await self.db.execute(
            text("""
                SELECT tenant_id, role FROM api_keys
                WHERE key_hash = :h AND is_active = TRUE
                  AND (expires_at IS NULL OR expires_at > NOW())
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
