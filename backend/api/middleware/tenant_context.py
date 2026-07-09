from uuid import UUID
from fastapi import Request
from contextvars import ContextVar

_tenant_id: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)


def get_current_tenant() -> UUID | None:
    return _tenant_id.get()


async def tenant_context_middleware(request: Request, call_next):
    tenant_header = request.headers.get("X-Tenant-ID")
    if tenant_header:
        try:
            token = _tenant_id.set(UUID(tenant_header))
            response = await call_next(request)
            _tenant_id.reset(token)
            return response
        except ValueError:
            pass
    return await call_next(request)
