-- Answer Engine: human review queue for ESCALATE_HUMAN_REVIEW decisions (Phase 2)
CREATE TABLE IF NOT EXISTS review_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_log_id UUID,
    tenant_id UUID NOT NULL,
    query_text TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'resolved', 'dismissed')),
    resolution_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS review_queue_status_idx
    ON review_queue (tenant_id, status, created_at);
