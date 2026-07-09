-- Answer Engine: per-tenant model registry (Phase 2)
-- Maps task_type -> model id, e.g. {"DRAFT": "gpt-4o", "VERIFY": "gpt-4o-mini"}
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS model_overrides JSONB NOT NULL DEFAULT '{}';
