-- Answer Engine Phase 3: immutable audit log + review workflow (assignment)

-- 1. Append-only audit log (immutability enforced by trigger)
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID,
    query_id UUID,
    event_type TEXT NOT NULL,
    decision TEXT,
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS audit_log_tenant_idx ON audit_log (tenant_id, created_at);

CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only (no UPDATE/DELETE)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_mutate ON audit_log;
CREATE TRIGGER audit_log_no_mutate
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();

-- 2. Review workflow: assignment + in_review status
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS assigned_to UUID;
ALTER TABLE review_queue DROP CONSTRAINT IF EXISTS review_queue_status_check;
ALTER TABLE review_queue ADD CONSTRAINT review_queue_status_check
    CHECK (status IN ('pending', 'in_review', 'resolved', 'dismissed'));
