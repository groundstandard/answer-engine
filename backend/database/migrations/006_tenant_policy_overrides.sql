-- 006: Per-tenant policy threshold overrides (active-learning auto-calibration).
-- The calibration loop writes numeric overrides here; the policy resolver merges
-- them on top of the tenant's named profile so thresholds can be tuned per tenant
-- without editing the shared YAML profiles.

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS policy_overrides JSONB NOT NULL DEFAULT '{}'::jsonb;
