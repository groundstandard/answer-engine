# Answer Engine — Evidence-Gated AI System
## Full Build Plan

---

## What We Are Building

A backend API service that sits between a user query and an LLM response.
Every answer passes through 4 gates before it reaches the user:

1. **Retrieval Gate** — retrieve supporting evidence from approved sources first
2. **Claim Gate** — decompose the draft answer into atomic factual claims
3. **Verification Gate** — score each claim against the evidence using NLI
4. **Policy Gate** — deterministic rules decide: VERIFIED / QUALIFIED / REFUSED

No answer reaches the user without passing all 4 gates.
No hallucination can pass through undetected.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Server | Python + FastAPI |
| Database | PostgreSQL (via SQLAlchemy async) |
| Vector Store | pgvector (local) → Qdrant (production) |
| Cache | Redis |
| LLM | Claude API (claude-sonnet-4-5 primary, claude-haiku-4-5 fallback) |
| Embeddings | text-embedding-3-small (OpenAI) or Claude |
| NLI Scoring | LLM-as-NLI (Phase 1), dedicated model (Phase 2) |
| Auth | JWT |
| Containerization | Docker + Docker Compose |
| Testing | pytest + pytest-asyncio |

---

## Folder Structure

```
answer-engine/
├── backend/
│   ├── api/
│   │   ├── app.py                  # FastAPI app factory
│   │   ├── routes/
│   │   │   ├── query.py            # POST /v1/query, GET /v1/query/{id}
│   │   │   ├── documents.py        # POST /v1/documents/index
│   │   │   ├── sources.py          # GET/POST /v1/sources
│   │   │   ├── feedback.py         # POST /v1/feedback
│   │   │   └── evaluations.py      # GET/POST /v1/evaluations
│   │   ├── middleware/
│   │   │   ├── auth.py             # JWT/API key auth
│   │   │   ├── rate_limiter.py     # Redis-backed rate limiting
│   │   │   └── tenant_context.py   # Tenant resolution
│   │   └── schemas/
│   │       ├── query.py            # Pydantic request/response schemas
│   │       ├── documents.py
│   │       └── evaluations.py
│   ├── services/
│   │   ├── classification/         # Classify query type + risk level
│   │   ├── retrieval/              # Hybrid vector + BM25 search
│   │   ├── indexing/               # Ingest + chunk + embed documents
│   │   ├── claims/                 # Extract atomic claims from draft
│   │   ├── verification/           # NLI scoring per claim vs evidence
│   │   ├── policy/                 # Deterministic gate logic
│   │   ├── composition/            # Render final response
│   │   └── evaluation/             # Telemetry + benchmarking
│   ├── orchestration/
│   │   └── pipeline.py             # Main pipeline controller
│   ├── models/                     # Pydantic/dataclass models
│   ├── database/                   # DB connection + repositories
│   └── config/                     # Settings, policy profiles, prompts
├── tests/
├── evaluation_datasets/
├── scripts/
├── docker/
├── docs/
├── .env.example
├── requirements.txt
├── pyproject.toml
└── docker-compose.yml
```

---

## Implementation Phases

### Phase 1 — MVP (Weeks 1–8)
Single-tenant. End-to-end pipeline working. Core goal: prove the verification architecture works.

**What gets built:**
- [ ] Project setup (venv, dependencies, Docker Compose)
- [ ] PostgreSQL schema + migrations (all tables from PRD Section 4)
- [ ] FastAPI app + all route stubs
- [ ] JWT auth middleware
- [ ] Request Classification Service (LLM-based)
- [ ] Retrieval Service (hybrid vector + BM25, no reranker yet)
- [ ] Document Indexing Service (text + PDF ingestion, chunking, embedding)
- [ ] Claim Extraction Service (LLM decomposes draft into atomic claims)
- [ ] Claim Verification Service (LLM-as-NLI)
- [ ] Policy Engine (deterministic rule gates)
- [ ] Response Composer (VERIFIED / QUALIFIED / REFUSED renderers)
- [ ] Model Orchestration Layer (single model, retry logic)
- [ ] Full pipeline trace logging to PostgreSQL
- [ ] Docker Compose local dev environment
- [ ] Unit tests for Policy Engine + Verification Algorithm
- [ ] Integration test: full pipeline end-to-end

**Milestone:** Query goes in → VERIFIED / QUALIFIED / REFUSED comes out with citations.

---

### Phase 2 — Production Beta (Weeks 9–20)
Multi-tenant. Configurable per tenant. Monitored.

**What gets built:**
- [ ] Multi-tenant support (isolated source namespaces per tenant)
- [ ] Per-tenant PolicyConfig (different thresholds per tenant)
- [ ] Cross-encoder reranker for retrieval quality
- [ ] Dedicated NLI model (replace LLM-as-NLI with faster/cheaper model)
- [ ] Source trust tiers + freshness policies
- [ ] POST /v1/feedback endpoint
- [ ] Evaluation framework (3 dataset types: factual, unanswerable, conflicting)
- [ ] Dashboard metrics (verified rate, refusal rate, unsupported claim rate)
- [ ] Rate limiting per tenant (Redis token bucket)
- [ ] Retry + fallback model chains
- [ ] Admin review queue for ESCALATE_HUMAN_REVIEW decisions

**Milestone:** Multiple tenants isolated. Evaluation framework running. >85% correct refusal rate.

---

### Phase 3 — Advanced (Weeks 21–36+)
Production-hardened. Domain-specialized. Active improvement loops.

**What gets built:**
- [ ] Multi-model orchestration (specialized models per task)
- [ ] Streaming responses (SSE) with per-claim verification events
- [ ] Human-in-the-loop review workflow
- [ ] Domain-specific policy packs (medical.yaml, legal.yaml, financial.yaml)
- [ ] Real-time source freshness monitoring + auto re-indexing
- [ ] Evaluation regression CI pipeline
- [ ] Full audit log with immutable trace storage
- [ ] Role-based access control (admin / reviewer / user / api_client)
- [ ] Cost optimization (route cheap queries to smaller models)

**Milestone:** >97% accuracy conditional on answering. <2% false confidence rate. P95 latency <8s.

---

## How We Start (Phase 1, Week 1)

### Step 1: Dev Environment Setup
```
1. Create Python virtual environment
2. Install dependencies (FastAPI, SQLAlchemy, asyncpg, pgvector, anthropic, etc.)
3. Set up Docker Compose (PostgreSQL + Redis + Qdrant)
4. Create .env file from .env.example
5. Run database migrations
```

### Step 2: Database Schema
Write and run all migrations from PRD Section 4:
- tenants, policy_configs, users
- queries, query_runs, model_configs
- sources, documents, document_chunks
- retrieved_evidence, claims, claim_verifications, claim_evidence_links
- policy_decisions, responses, evaluation_runs, evaluation_results, feedback

### Step 3: FastAPI App + Route Stubs
- app.py with middleware wired up
- All 5 route files with stub handlers (return 501 Not Implemented)
- Pydantic schemas for all request/response types

### Step 4: Pipeline Services (one by one)
Build each service in pipeline order:
1. Classification Service
2. Retrieval Service
3. Indexing Service
4. Claim Extraction Service
5. Claim Verification Service
6. Policy Engine
7. Response Composer
8. Pipeline Controller (wires all services together)

### Step 5: First Working Query
Wire up POST /v1/query → run_pipeline() → return FinalResponse.
Test with a simple factual query against a seeded document.

---

## Key Design Rules (from PRD)

1. **No stage can be skipped** — even if model is confident
2. **Policy Engine is deterministic** — no model involved in the final gate
3. **Verification is never done by the same model that generates claims** — prevents self-confirmation bias
4. **Fluency ≠ correctness** — a well-formed sentence with no evidence support is treated as a fabrication
5. **Never silent degrade** — always raise structured errors, never return hallucinated fallback

---

## API Endpoints (Phase 1)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /v1/query | Submit query → returns VERIFIED/QUALIFIED/REFUSED |
| GET | /v1/query/{id} | Get full pipeline trace for a query |
| POST | /v1/documents/index | Index a document into evidence store |
| GET | /v1/sources | List evidence sources for tenant |
| POST | /v1/sources | Register new evidence source |
| POST | /v1/feedback | Submit feedback on a response |
| GET | /health | Health check |

---

## Response States

**VERIFIED** — all critical claims supported by retrieved evidence above threshold
```json
{ "final_decision": "VERIFIED", "response_text": "...", "citations": [...] }
```

**QUALIFIED** — claims partially supported, returned with explicit uncertainty markers
```json
{ "final_decision": "QUALIFIED", "response_text": "...", "uncertainty_notes": [...] }
```

**REFUSED** — evidence insufficient, contradictory, or stale — system declines
```json
{ "final_decision": "REFUSED", "refusal_reason": "..." }
```

---

## Dependencies (requirements.txt)

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.29.0
pgvector==0.3.2
redis==5.1.0
anthropic==0.39.0
openai==1.54.0
httpx==0.27.2
pydantic==2.9.2
pydantic-settings==2.6.1
python-jose[cryptography]==3.3.0
alembic==1.13.3
pytest==8.3.3
pytest-asyncio==0.24.0
python-multipart==0.0.12
python-dotenv==1.0.1
tiktoken==0.8.0
numpy==2.1.3
```

---

## Simula Natin Ngayon

**Week 1 tasks (in order):**
1. `requirements.txt` + `pyproject.toml`
2. `.env.example`
3. `docker-compose.yml` (PostgreSQL + Redis + Qdrant)
4. `backend/config/settings.py` (Pydantic settings from env)
5. `backend/database/connection.py` (async DB pool)
6. `backend/database/migrations/` (Alembic + full schema)
7. `backend/api/app.py` (FastAPI factory)
8. All route stubs + Pydantic schemas

Sabi mo simulan na — magsisimula na tayo sa Week 1 tasks. Okay lang ba?
