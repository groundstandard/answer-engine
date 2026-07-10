from fastapi import Request, HTTPException, status
from jose import JWTError, jwt

from backend.config.settings import settings


async def _authenticate(request: Request) -> dict:
    """
    Resolve caller claims from EITHER a Bearer JWT or an X-API-Key header
    (PRD §3.1: JWT or API key). Returns claims incl. tenant_id and role.
    """
    # 1. Bearer JWT
    authz = request.headers.get("Authorization", "")
    if authz.lower().startswith("bearer "):
        token = authz.split(" ", 1)[1].strip()
        try:
            return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    # 2. X-API-Key
    api_key = request.headers.get("X-API-Key", "").strip()
    if api_key:
        from backend.database.connection import AsyncSessionLocal
        from backend.database.repositories.api_key_repo import ApiKeyRepository
        try:
            async with AsyncSessionLocal() as session:
                claims = await ApiKeyRepository(session).verify(api_key)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Auth store unavailable: {e}")
        if not claims:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        return claims

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing credentials (Bearer token or X-API-Key)")


async def require_auth(request: Request):
    """Any authenticated caller (no-op unless AUTH_REQUIRED)."""
    if not settings.AUTH_REQUIRED:
        return None
    return await _authenticate(request)


def require_role(*allowed: str):
    """Dependency factory enforcing the caller's role (no-op unless AUTH_REQUIRED)."""
    async def dependency(request: Request):
        if not settings.AUTH_REQUIRED:
            return None
        claims = await _authenticate(request)
        role = claims.get("role", "api_client")
        if role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires one of roles: {', '.join(allowed)}",
            )
        return claims
    return dependency
