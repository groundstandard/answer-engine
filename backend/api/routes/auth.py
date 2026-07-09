from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from jose import jwt

from backend.config.settings import settings

router = APIRouter()


_VALID_ROLES = ("admin", "reviewer", "user", "api_client")


class TokenRequest(BaseModel):
    tenant_id: UUID
    role: str = "api_client"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/auth/token", response_model=TokenResponse)
async def issue_token(body: TokenRequest, request: Request):
    """Mint a tenant-scoped, role-bearing JWT. Guarded by X-Service-Key when SERVICE_KEY is set."""
    if settings.SERVICE_KEY and request.headers.get("X-Service-Key") != settings.SERVICE_KEY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing service key")
    if body.role not in _VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role must be one of {_VALID_ROLES}")

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "tenant_id": str(body.tenant_id),
        "role": body.role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return TokenResponse(access_token=token, expires_in=settings.JWT_EXPIRE_MINUTES * 60)
