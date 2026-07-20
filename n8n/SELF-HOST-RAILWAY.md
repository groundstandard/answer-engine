# Self-hosting n8n on Railway (move off n8n Cloud)

Why: n8n Cloud bills per **execution**. Each Answer Engine question = ~6–7 executions
(the PRD pipeline: classify → draft+claims → verify → compose + 1 embedding), so the
Cloud plan caps out fast. A **self-hosted n8n on Railway** is a flat machine cost with
**no per-execution limit** — cheaper and reliable at scale.

Result: the two webhooks move from `groundstandard.app.n8n.cloud` to our own Railway
n8n domain, and the Answer Engine is pointed at the new URLs. No app code changes.

---

## 1. Deploy n8n on Railway

Easiest path — Railway's official n8n template:
1. Railway → **New Project → Deploy a template → search "n8n"** → deploy.
   - It provisions the **n8n** service + a **Postgres** DB + a persistent volume.
2. If deploying the Docker image manually instead: image `n8nio/n8n:latest`, attach a
   **Volume** mounted at `/home/node/.n8n`, and add a **Postgres** service.

### Required environment variables (n8n service)
| Var | Value | Why |
|---|---|---|
| `N8N_ENCRYPTION_KEY` | a fixed random 32+ char string | Encrypts stored credentials. **Must never change** or credentials break. |
| `WEBHOOK_URL` | `https://<your-n8n>.up.railway.app/` | So webhook URLs resolve to the public domain. |
| `N8N_HOST` | `<your-n8n>.up.railway.app` | Public host. |
| `N8N_PROTOCOL` | `https` | |
| `N8N_PORT` | `5678` (Railway maps its `$PORT`; the template handles this) | |
| `N8N_BASIC_AUTH_ACTIVE` | `true` | Locks the editor. |
| `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` | your choice | Editor login. |
| `DB_TYPE` | `postgresdb` | Persist workflows/executions in Postgres. |
| `DB_POSTGRESDB_HOST/PORT/DATABASE/USER/PASSWORD` | from the Railway Postgres | |
| `EXECUTIONS_DATA_PRUNE` | `true` | Keep the DB lean. |
| `EXECUTIONS_DATA_MAX_AGE` | `336` (hours = 14 days) | Auto-delete old execution logs. |

3. Deploy → open the generated Railway domain → finish n8n's first-run owner setup.

## 2. Import the two workflows
In the new n8n: **Workflows → Import from File** for each:
- `n8n/answer-engine-llm.json`  → creates **Answer Engine — LLM**
- `n8n/answer-engine-embeddings.json` → creates **Answer Engine — Embeddings**

## 3. Add the OpenAI credential (Bobby inputs this)
Credentials do NOT transfer between instances (encrypted per-instance). In the new n8n:
- **Credentials → New → OpenAI** → paste the OpenAI **API key** → Save.
- Open each workflow's OpenAI node and select this credential.
- (Leave the Organization ID blank unless the key requires a specific org.)

## 4. Activate both workflows
Toggle each workflow **Active** (top-right). Confirm the production webhook paths:
- `https://<your-n8n>.up.railway.app/webhook/answer-engine-llm`
- `https://<your-n8n>.up.railway.app/webhook/answer-engine-embed`

## 5. Point the Answer Engine at the new URLs
On the **Answer Engine** Railway service → Variables, update:
```
N8N_LLM_WEBHOOK_URL=https://<your-n8n>.up.railway.app/webhook/answer-engine-llm
N8N_EMBEDDING_WEBHOOK_URL=https://<your-n8n>.up.railway.app/webhook/answer-engine-embed
```
Redeploy the Answer Engine. Done — no code changes.

## 6. Verify
- Probe embeddings: `POST /webhook/answer-engine-embed` with `{"input":["test"]}` → expect a 1536-number array.
- Then re-run the legal test set → should pass with no execution-limit errors.

---

## Cost (self-hosted vs Cloud)
- **Self-hosted on Railway:** flat **~$5–20/mo** for the n8n machine + **~$0–5/mo** Postgres.
  **No per-execution cost** — executions limited only by machine capacity, not a plan cap.
- **vs n8n Cloud:** ~$20–60/mo AND capped executions (~2,500–10,000/mo), which we blew
  through in one test set.
- Net: **lower fixed cost + effectively unlimited executions** — the right long-term setup.

*(Separate from n8n: OpenAI usage — embeddings are ~free; the chat model is a few cents
per question. That's pay-per-use regardless of where n8n runs.)*
