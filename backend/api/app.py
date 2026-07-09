import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager

_STATIC_DIR = Path(__file__).parent / "static"
from backend.api.routes import query, documents, sources, feedback, evaluations, metrics, auth, admin
from backend.api.middleware.rate_limiter import rate_limiter
from backend.api.deps import require_auth, require_role
from backend.database.connection import init_db
from backend.config.settings import settings

_RATE_LIMIT_EXEMPT = ("/health", "/docs", "/openapi.json", "/redoc", "/dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as e:
        print(f"[WARN] DB init skipped: {e}")
    yield


def _setup_observability() -> None:
    """Structured logging + optional Sentry alerting (PRD Phase 2)."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
            logging.getLogger(__name__).info("Sentry alerting enabled")
        except Exception as e:  # noqa: BLE001 — never let telemetry break startup
            logging.getLogger(__name__).warning("Sentry DSN set but sentry_sdk unavailable: %s", e)


def create_app() -> FastAPI:
    _setup_observability()
    app = FastAPI(
        title="Evidence-Gated AI System",
        description="Reliability gateway that enforces evidence verification before any LLM response reaches a user.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def rate_limit(request, call_next):
        if request.url.path not in _RATE_LIMIT_EXEMPT:
            try:
                await rate_limiter.check(request)
            except HTTPException as e:
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        return await call_next(request)

    # Token minting must stay open (you can't have a token yet to get a token).
    app.include_router(auth.router, prefix="/v1", tags=["Auth"])

    # All other /v1 routes are guarded by require_auth (no-op unless AUTH_REQUIRED).
    guarded = [Depends(require_auth)]
    app.include_router(query.router, prefix="/v1", tags=["Query"], dependencies=guarded)
    app.include_router(documents.router, prefix="/v1", tags=["Documents"], dependencies=guarded)
    app.include_router(sources.router, prefix="/v1", tags=["Sources"], dependencies=guarded)
    app.include_router(feedback.router, prefix="/v1", tags=["Feedback"], dependencies=guarded)
    app.include_router(evaluations.router, prefix="/v1", tags=["Evaluations"], dependencies=guarded)
    # Admin/analytics surfaces require an elevated role (when auth is enforced).
    staff = [Depends(require_role("admin", "reviewer"))]
    app.include_router(metrics.router, prefix="/v1", tags=["Metrics"], dependencies=staff)
    app.include_router(admin.router, prefix="/v1", tags=["Admin"], dependencies=staff)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard():
        return FileResponse(_STATIC_DIR / "dashboard.html")

    return app


app = create_app()
