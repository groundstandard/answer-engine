import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from contextlib import asynccontextmanager

_STATIC_DIR = Path(__file__).parent / "static"
from backend.api.routes import query, documents, sources, feedback, evaluations, metrics, auth, admin
from backend.api.middleware.rate_limiter import rate_limiter
from backend.api.deps import require_auth, require_role
from backend.database.connection import init_db
from backend.config.settings import settings

_RATE_LIMIT_EXEMPT = ("/health", "/docs", "/openapi.json", "/redoc", "/dashboard", "/guide", "/signup", "/static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    try:
        await init_db()
    except Exception as e:
        print(f"[WARN] DB init skipped: {e}")

    monitor_task = None
    if settings.ENABLE_FRESHNESS_MONITOR:
        from backend.services.monitoring.freshness_monitor import freshness_monitor_loop
        monitor_task = asyncio.create_task(freshness_monitor_loop())

    yield

    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


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
        description=(
            "Reliability gateway that enforces evidence verification before any LLM "
            "response reaches a user.\n\n"
            "🔑 **[Get an API key →](/signup)** — free self-service signup.  •  "
            "📘 **[Integration Guide →](/guide)** — how to connect your app.  •  "
            "📊 **[Admin Dashboard →](/dashboard)**"
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,   # replaced by a branded custom /docs below
        redoc_url=None,
    )

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def rate_limit(request, call_next):
        if not request.url.path.startswith(_RATE_LIMIT_EXEMPT):
            try:
                await rate_limiter.check(request)
            except HTTPException as e:
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        return await call_next(request)

    # Token minting must stay open (you can't have a token yet to get a token).
    app.include_router(auth.router, prefix="/v1", tags=["Auth"])

    # Developer-facing endpoints shown in /docs are OPEN for now (no sign-in) so the
    # API can be viewed and tried while it's not in real use. Re-add `guarded` before
    # going live. The dashboard's admin surfaces below stay protected regardless.
    open_dev = []
    app.include_router(query.router, prefix="/v1", tags=["Query"], dependencies=open_dev)
    app.include_router(documents.router, prefix="/v1", tags=["Documents"], dependencies=open_dev)
    app.include_router(sources.router, prefix="/v1", tags=["Sources"], dependencies=open_dev)
    app.include_router(feedback.router, prefix="/v1", tags=["Feedback"], dependencies=open_dev)
    app.include_router(evaluations.router, prefix="/v1", tags=["Evaluations"], dependencies=open_dev)
    # Admin/analytics surfaces (the dashboard) still require sign-in.
    staff = [Depends(require_role("admin", "reviewer"))]
    app.include_router(metrics.router, prefix="/v1", tags=["Metrics"], dependencies=staff)
    app.include_router(admin.router, prefix="/v1", tags=["Admin"], dependencies=staff)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard():
        return FileResponse(_STATIC_DIR / "dashboard.html", headers={"Cache-Control": "no-store"})

    @app.get("/guide", include_in_schema=False)
    async def guide():
        return FileResponse(_STATIC_DIR / "guide.html", headers={"Cache-Control": "no-store"})

    @app.get("/signup", include_in_schema=False)
    async def signup_page():
        return FileResponse(_STATIC_DIR / "signup.html", headers={"Cache-Control": "no-store"})

    @app.get("/docs", include_in_schema=False)
    async def custom_docs():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Answer Engine — API Reference",
            swagger_css_url="/static/swagger-theme.css",
        )

    return app


app = create_app()
