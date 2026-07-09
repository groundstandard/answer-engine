# Answer Engine — n8n Setup (for Bobby)

The Answer Engine sends every AI call through your n8n so the OpenAI credentials
stay in n8n (nothing sensitive lives in the backend). Two workflows to import.

Both reuse your existing **"OpenAi account"** credential — no new keys needed.

---

## 1. Import the two workflows

In n8n: **Workflows → ⋮ → Import from File**, then pick each file:

- `answer-engine-llm.json`  → creates **Answer Engine — LLM**
- `answer-engine-embeddings.json` → creates **Answer Engine — Embeddings**

If the OpenAI credential doesn't auto-link, open the HTTP Request node in each
workflow and re-select your **OpenAi account** credential.

## 2. Activate both

Toggle each workflow to **Active** (top-right). That turns on the production
webhook URLs:

- LLM:        `https://<your-n8n-host>/webhook/answer-engine-llm`
- Embeddings: `https://<your-n8n-host>/webhook/answer-engine-embed`

## 3. Send Angelo the two URLs

He pastes them into the Answer Engine `.env`:

```
N8N_LLM_WEBHOOK_URL=https://<your-n8n-host>/webhook/answer-engine-llm
N8N_EMBEDDING_WEBHOOK_URL=https://<your-n8n-host>/webhook/answer-engine-embed
```

(Optional) To lock the webhooks down, add a shared secret: put a header check at
the top of each workflow, and give Angelo the header name + value for
`N8N_WEBHOOK_AUTH_HEADER` / `N8N_WEBHOOK_AUTH_TOKEN`.

---

## The contract (what each workflow does)

### LLM workflow
**Receives:**
```json
{ "task_type": "DRAFT", "model": "...", "system": "...", "prompt": "...", "temperature": 0.0, "max_tokens": 4096 }
```
**Returns:**
```json
{ "text": "<the model's raw text answer>" }
```
It calls OpenAI `gpt-4o-mini`. To use a stronger model, change `'gpt-4o-mini'`
in the **OpenAI Chat Completion** node's body to e.g. `'gpt-4o'`.

### Embeddings workflow
**Receives:**
```json
{ "input": ["text one", "text two"] }
```
**Returns:**
```json
{ "embeddings": [[...1536 floats...], [...]] }
```
It calls OpenAI `text-embedding-3-small` (1536 dims). **Do not change this model** —
it must match what the database and search were built for, or search breaks.

---

## Quick test (after activating)

```bash
# LLM
curl -X POST https://<your-n8n-host>/webhook/answer-engine-llm \
  -H "Content-Type: application/json" \
  -d '{"task_type":"DRAFT","system":"Reply with JSON.","prompt":"Say {\"draft_answer\":\"hello\"}","max_tokens":50}'
# expect: {"text":"{\"draft_answer\":\"hello\"}"}

# Embeddings
curl -X POST https://<your-n8n-host>/webhook/answer-engine-embed \
  -H "Content-Type: application/json" \
  -d '{"input":["hello world"]}'
# expect: {"embeddings":[[0.01, -0.02, ... 1536 numbers ...]]}
```

If both return the shapes above, the Answer Engine is ready to point at n8n.
