from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from jose import jwt

from backend.config.settings import settings

router = APIRouter()


class TokenRequest(BaseModel):
    tenant_id: UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/auth/token", response_model=TokenResponse)
async def issue_token(body: TokenRequest, request: Request):
    """Mint a tenant-scoped JWT. Guarded by X-Service-Key when SERVICE_KEY is set."""
    if settings.SERVICE_KEY and request.headers.get("X-Service-Key") != settings.SERVICE_KEY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing service key")

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "tenant_id": str(body.tenant_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return TokenResponse(access_token=token, expires_in=settings.JWT_EXPIRE_MINUTES * 60)
