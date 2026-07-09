from fastapi import Request, HTTPException, status
from jose import JWTError, jwt

from backend.config.settings import settings


def _decode(request: Request) -> dict:
    authz = request.headers.get("Authorization", "")
    if not authz.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authz.split(" ", 1)[1].strip()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


async def require_auth(request: Request):
    """Any authenticated caller (no-op unless AUTH_REQUIRED)."""
    if not settings.AUTH_REQUIRED:
        return None
    return _decode(request)


def require_role(*allowed: str):
    """Dependency factory enforcing the token's role (no-op unless AUTH_REQUIRED)."""
    async def dependency(request: Request):
        if not settings.AUTH_REQUIRED:
            return None
        claims = _decode(request)
        role = claims.get("role", "api_client")
        if role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires one of roles: {', '.join(allowed)}",
            )
        return claims
    return dependency
