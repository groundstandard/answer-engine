-- 007: Optional expiry for API keys.
-- NULL expires_at means the key never expires (e.g. the owner's key). Dev keys can
-- be minted with a finite lifetime so shared access auto-revokes.

ALTER TABLE api_keys
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
