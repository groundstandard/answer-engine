from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://ae_user:ae_password@localhost:5432/answer_engine"
    REDIS_URL: str = "redis://localhost:6379"

    VECTOR_STORE_BACKEND: str = "pgvector"
    QDRANT_URL: str = "http://localhost:6333"
    VECTOR_STORE_API_KEY: str = ""

    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    LLM_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-5-20251001"
    LLM_FALLBACK_MODEL: str = "claude-haiku-4-5-20251001"
    # Optional per-task specialized-model routing, e.g.
    # TASK_MODELS='{"VERIFY":"my-nli-model","RERANK":"my-rerank-model"}'
    TASK_MODELS: dict = {}

    # n8n webhook routing — when set, all model/embedding calls go through Bobby's
    # n8n workflows (credentials stay in n8n). Empty = fall back to direct SDK.
    N8N_LLM_WEBHOOK_URL: str = ""
    N8N_EMBEDDING_WEBHOOK_URL: str = ""
    N8N_WEBHOOK_AUTH_HEADER: str = ""  # e.g. "Authorization" or "X-Api-Key"
    N8N_WEBHOOK_AUTH_TOKEN: str = ""   # value sent in the header above

    JWT_SECRET: str = "changeme-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # When True, all /v1 routes require a valid Bearer token. Default False so
    # local/dev + internal use works without tokens; flip on for external beta.
    AUTH_REQUIRED: bool = False
    # If set, minting a token via /v1/auth/token requires this shared key in
    # the X-Service-Key header (prevents anyone issuing tenant tokens).
    SERVICE_KEY: str = ""

    RATE_LIMIT_PER_MINUTE: int = 60

    RETRIEVAL_TOP_K: int = 20
    EVIDENCE_BUNDLE_SIZE: int = 10
    PIPELINE_TIMEOUT_SECONDS: int = 60
    MAX_MODEL_RETRIES: int = 3

    ENABLE_RERANKER: bool = False
    ENABLE_STREAMING: bool = False

    # Cost optimization: route low-risk queries' generation tasks to the cheaper
    # fallback model. Verification always stays on its configured model.
    ENABLE_COST_ROUTING: bool = True
    COST_ROUTING_RISK_THRESHOLD: float = 0.4

    # Extra cross-evidence contradiction pass (one LLM call) before the policy gate.
    ENABLE_CONTRADICTION_CHECK: bool = False
    # Background freshness monitor: periodically flags stale sources into the audit log.
    ENABLE_FRESHNESS_MONITOR: bool = False
    FRESHNESS_CHECK_INTERVAL_MIN: int = 60
    FRESHNESS_STALE_DAYS: int = 30

    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""

    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def llm_api_key(self) -> str:
        return self.LLM_API_KEY

    @property
    def openai_api_key(self) -> str:
        return self.OPENAI_API_KEY

    @property
    def llm_model(self) -> str:
        return self.LLM_MODEL

    @property
    def llm_fallback_model(self) -> str:
        return self.LLM_FALLBACK_MODEL

    @property
    def jwt_secret(self) -> str:
        return self.JWT_SECRET

    @property
    def jwt_algorithm(self) -> str:
        return self.JWT_ALGORITHM

    @property
    def vector_store_backend(self) -> str:
        return self.VECTOR_STORE_BACKEND

    @property
    def qdrant_url(self) -> str:
        return self.QDRANT_URL

    @property
    def rate_limit_per_minute(self) -> int:
        return self.RATE_LIMIT_PER_MINUTE


settings = Settings()
