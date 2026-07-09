from fastapi import Request, HTTPException, status
from jose import JWTError, jwt

from backend.config.settings import settings


async def require_auth(request: Request):
    """
    FastAPI dependency guarding /v1 routes.

    If AUTH_REQUIRED is False (default), it is a no-op so local/internal use
    works without tokens. When True, a valid Bearer JWT is mandatory and its
    claims (incl. tenant_id) are returned.
    """
    if not settings.AUTH_REQUIRED:
        return None

    authz = request.headers.get("Authorization", "")
    if not authz.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    token = authz.split(" ", 1)[1].strip()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
