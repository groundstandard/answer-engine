from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.api.routes import query, documents, sources, feedback, evaluations
from backend.database.connection import init_db
from backend.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as e:
        print(f"[WARN] DB init skipped: {e}")
    yield


def create_app() -> FastAPI:
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

    app.include_router(query.router, prefix="/v1", tags=["Query"])
    app.include_router(documents.router, prefix="/v1", tags=["Documents"])
    app.include_router(sources.router, prefix="/v1", tags=["Sources"])
    app.include_router(feedback.router, prefix="/v1", tags=["Feedback"])
    app.include_router(evaluations.router, prefix="/v1", tags=["Evaluations"])

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
