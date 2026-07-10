from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from jose import jwt

from backend.config.settings import settings
from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.api_key_repo import ApiKeyRepository
from backend.database.repositories.tenant_repo import TenantRepository

router = APIRouter()

_SIGNUP_KEY_DAYS = 90  # self-service keys auto-expire so abandoned ones don't linger


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


class SignupRequest(BaseModel):
    email: str
    app_name: str


@router.post("/signup", status_code=201)
async def developer_signup(body: SignupRequest):
    """Public self-service: a developer gets their OWN tenant + api_client key.
    Guardrails: role is always api_client, the key expires, and this route is
    rate-limited. No admin/reviewer access can be self-issued."""
    email = (body.email or "").strip()
    app = (body.app_name or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid email is required")
    if len(app) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "App name is required")
    try:
        async with AsyncSessionLocal() as session:
            tenant_id = await TenantRepository(session).create_tenant(f"{app} ({email})")
            _, raw = await ApiKeyRepository(session).create(
                tenant_id, "api_client", f"{app} <{email}>", _SIGNUP_KEY_DAYS
            )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Signup failed: {e}")
    return {
        "tenant_id": str(tenant_id),
        "api_key": raw,
        "role": "api_client",
        "expires_in_days": _SIGNUP_KEY_DAYS,
    }


class ApiKeyRequest(BaseModel):
    tenant_id: UUID
    role: str = "api_client"
    name: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: UUID
    api_key: str  # shown ONCE — only the hash is stored
    role: str


@router.post("/auth/api-keys", response_model=ApiKeyResponse, status_code=201)
async def create_api_key(body: ApiKeyRequest, request: Request):
    """Mint a long-lived API key (sent as X-API-Key). Guarded by X-Service-Key when set."""
    if settings.SERVICE_KEY and request.headers.get("X-Service-Key") != settings.SERVICE_KEY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing service key")
    if body.role not in _VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role must be one of {_VALID_ROLES}")
    try:
        async with AsyncSessionLocal() as session:
            key_id, raw = await ApiKeyRepository(session).create(body.tenant_id, body.role, body.name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Could not create API key: {e}")
    return ApiKeyResponse(id=key_id, api_key=raw, role=body.role)
