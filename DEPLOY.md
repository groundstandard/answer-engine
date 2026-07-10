# Answer Engine — Deploy to Railway

Persistent web service (FastAPI). Supabase (DB) and n8n (AI) stay where they are —
only this backend + dashboard get hosted.

## 1. Create the service
1. Railway → **New Project** → **Deploy from GitHub repo** → `groundstandard/answer-engine`, branch `main`.
2. Railway auto-detects Python (Nixpacks) and reads `railway.json`:
   - start: `python -m uvicorn backend.api.app:app --host 0.0.0.0 --port $PORT`
   - healthcheck: `/health`
3. Settings → **Networking** → **Generate Domain** to get a public URL.

## 2. Environment variables (Railway → Variables)
`.env` is gitignored, so set these in Railway:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase **session pooler** URL (same as local `.env`) |
| `N8N_LLM_WEBHOOK_URL` | `https://groundstandard.app.n8n.cloud/webhook/answer-engine-llm` |
| `N8N_EMBEDDING_WEBHOOK_URL` | *(leave blank until Bobby sends the OpenAI org-id)* |
| `AUTH_REQUIRED` | `true` |
| `SERVICE_KEY` | generate (see below) — guards key/token minting |
| `JWT_SECRET` | generate — signs JWTs |
| `ENABLE_FRESHNESS_MONITOR` | `true` *(optional — background stale-source scan)* |
| `ALLOWED_ORIGINS` | JSON list of browser origins that call the API, e.g. `["https://your-frontend.com"]` (dashboard is same-origin, so optional) |

Generate secrets locally:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # run twice: SERVICE_KEY + JWT_SECRET
```

## 3. Verify
- `GET  https://<domain>/health` → `{"status":"ok"}`
- `GET  https://<domain>/docs` → branded Swagger
- `GET  https://<domain>/dashboard` → admin dashboard

## 4. Because AUTH_REQUIRED=true — mint a key, then use the dashboard
The `/v1/auth/*` routes stay open (you can't need a token to get one). Mint an admin
API key with the service key:

```bash
curl -X POST https://<domain>/v1/auth/api-keys \
  -H "X-Service-Key: <SERVICE_KEY>" -H "Content-Type: application/json" \
  -d '{"tenant_id":"3aa67dce-9bbf-4a83-8d77-d461fabd6726","role":"admin","name":"dashboard"}'
```

Response returns `api_key` (starts with `ae_`) **once**. Open `/dashboard`, paste it into
the **Key** field (top-right), click **Save**. All calls now authenticate (JWT also works —
mint via `POST /v1/auth/token`).

Other apps call the API with header `X-API-Key: ae_...` (or `Authorization: Bearer <jwt>`).

## Notes
- Long queries (~15s), SSE streaming, and the background freshness monitor all work on
  Railway (persistent process — no serverless timeout).
- Semantic/vector search stays off until `N8N_EMBEDDING_WEBHOOK_URL` is set; retrieval
  runs on BM25 keyword search until then.
