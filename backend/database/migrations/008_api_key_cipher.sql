-- 008: Store an encrypted copy of each API key so the owner (admin) can view the
-- full key later. Encrypted at rest with a server-side secret (env, not in the DB);
-- the sha256 hash in key_hash is still what auth checks against. Keys created before
-- this migration have NULL key_cipher and can only be shown masked.

ALTER TABLE api_keys
    ADD COLUMN IF NOT EXISTS key_cipher TEXT;
