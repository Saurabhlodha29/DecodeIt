# STEPS — How DecodeIt (CodeRecon) Was Built

This file is the build log of the project. Each phase records **what we built, what we decided, and why**, so that anyone reading it from top to bottom can understand how the project came to be and could rebuild it from scratch.

Conventions used below:

- **Implemented** = exists in the codebase and works.
- **Decided** = agreed design that is not built yet (it is built in a later phase).
- Unchecked boxes `[ ]` are open follow-ups. Tick them off as they are done.

---

## Phase 0 — Foundation

**Status:** Complete
**Date completed:** 2026-09-20
**Goal:** Lock the problem, the architecture and the stack, and get a minimal but correct backend skeleton running, without building any real features yet.

### 0.1 Problem selection

- Hackathon: Bennett University Hackathon 2026 (Microsoft Innovate 2026), 15-day deadline.
- Problem statement chosen: **PS 3 — "Decoding the 20-Year-Old System"**, i.e. helping people understand and explain legacy codebases.
- Product direction: an AI-powered **Codebase Archaeologist (CodeRecon / DecodeIt)** that:
  1. explains legacy repositories,
  2. traces code paths (who calls what, which tables are touched),
  3. later supports verified human corrections (a reviewer approves or fixes an explanation).
- Scope decision: support **Java and Python only**. Doing two languages well is better than doing five badly.

### 0.2 Team and roles

| Member | Responsibility |
|---|---|
| Saurabh | Backend, AI, architecture, overall technical integration |
| Pragya | Smaller backend tasks and FastAPI support (learning FastAPI first) |
| Aditya | Frontend: React + TypeScript |

### 0.3 Architecture principles and decisions

**Principle:** do not rely on the LLM alone. Combine LLM reasoning with structured code intelligence (parsing, symbols, relationships) and retrieval, so answers are grounded in real code.

| Area | Decision | Reason |
|---|---|---|
| Backend | FastAPI + LangChain + LangGraph | Async API with streaming, and an explicit, resumable agent flow |
| Database | Supabase (PostgreSQL) as the single system of record | One database means transactions, RLS and simple deployment |
| Graph | Store nodes and edges in Postgres; load a repo's graph into NetworkX in memory for multi-hop analysis. **No Neo4j** initially | A per-repo call graph is small; a third database is too much for 3 people in 15 days |
| Code model | Files → symbols → relationships (edges) → code chunks | Chunks are semantic units with exact line ranges, which allows reliable citations |
| Ingestion | Bulk ingestion will **clone the repo in a worker** (`git clone --depth 1`) | Faster and more reliable than fetching files one by one |
| MCP | Used for **interactive tool/resource access only**, not bulk ingestion | MCP is the wrong tool for bulk transfer |
| LLM (dev) | NVIDIA NIM via LangChain (`openai/gpt-oss-20b` for now) | Cheap to iterate with; keeps Groq/HuggingFace quotas for later |
| LLM (demo) | Qwen 3.x on HuggingFace for the final demo | Most capable option; to be verified with a real call before relying on it |
| Embeddings | Voyage AI code embeddings, **1024 dimensions** (`chunks.embedding`) | Code-specific retrieval quality; 1024 is a good quality/storage balance |
| Retrieval (planned) | Postgres vector search + full-text search, fused later | Embeddings alone are weak on exact identifiers |
| Auth | Supabase Auth | Managed users, no custom auth code |
| Authorization | PostgreSQL Row Level Security (RLS) | Ownership enforced in the database, not only in app code |

**Note on NVIDIA NIM limits:** the free tier is rate-limited (about 40 requests per minute), not unlimited. The LLM gateway will need a client-side rate limiter, retries and caching before the agent is built.

### 0.4 Repository and environment setup

- GitHub repository created, teammates added as collaborators.
- Python virtual environment created locally (each member creates their own; it is never committed).
- `.gitignore` excludes the virtual environment, `__pycache__`, `.env` files, editor and OS files.
- `README.md` documents the clone, venv, install and branch/PR workflow for the team.
- Monorepo layout:

```
DecodeIt/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── config.py          # loads environment variables
│   │   ├── database.py        # Supabase client
│   │   ├── api/routes/        # health.py, repos.py
│   │   ├── llm/gateway.py     # NVIDIA NIM LLM client
│   │   ├── agents/            # (planned) LangGraph orchestration
│   │   ├── graph/             # (planned) code graph builder and queries
│   │   ├── guardrails/        # (planned) redaction, injection handling
│   │   ├── ingestion/         # (planned) clone + parse repos
│   │   ├── retrieval/         # (planned) hybrid search
│   │   ├── verify/            # (planned) citation verifier
│   │   └── worker/            # (planned) job queue consumer
│   └── scripts/
│       └── init_db.py         # applies db/migrations to Supabase
├── db/migrations/             # SQL schema migrations (001_initial_schema.sql)
├── frontend/                  # React + TypeScript (planned)
├── evals/                     # (planned) golden set and metrics
├── docs/
├── requirements.txt
├── .env.example
└── STEPS.md                   # this file
```

### 0.5 Database (Supabase)

Tables created in Phase 0 (the minimum needed for ingestion and code intelligence):

| Table | Purpose |
|---|---|
| `profiles` | App-level user record, linked to Supabase `auth.users` |
| `repos` | A repository a user has added (URL, name, language, default branch) |
| `commits` | One ingested snapshot of a repo; everything downstream belongs to one commit |
| `jobs` | Postgres-backed job queue for background work |
| `files` | Source files of a commit (path, content, hash) |
| `symbols` | Functions, methods, classes and DB tables, with line ranges and a code hash |
| `code_edges` | Relationships between symbols (calls, imports, reads/writes), each with a confidence score |
| `chunks` | Code chunks with a 1024-dimension embedding and a full-text search column |

Ownership chain: `auth.users → profiles → repos → commits → files / symbols / chunks`.

Intentionally postponed to the phase that needs them: `chat_sessions`, `messages`, `explanations`, `verified_notes`, `answer_cache`, `eval_runs`, `audit_log`.

The schema is stored in the repository as `db/migrations/001_initial_schema.sql`, and `backend/scripts/init_db.py` applies it, so anyone can recreate the database (see 0.12). It matches the schema exported from Supabase, but it does not yet include RLS policies, indexes or unique constraints; those come as later migrations.

Database capabilities planned: vector search (pgvector), full-text search, graph-like traversal with recursive queries, and indexes on the columns used for traversal and search.

### 0.6 Security and keys

- Supabase Auth manages users.
- **Decided:** the React app uses the Supabase **publishable** key; the FastAPI backend uses the Supabase **secret** key.
- The secret key stays **backend-only** and is never exposed to React or committed.
- **Decided (RLS model):** requests made on behalf of a user carry that user's auth context so RLS applies; privileged backend or worker operations (such as ingestion) may deliberately use the secret key, because the secret key bypasses RLS.
- All secrets live in `.env`, which is git-ignored.

### 0.7 Configuration

- Environment variables are loaded from `.env` in `backend/app/config.py`.
- Required variables: `NVIDIA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `VOYAGE_API_KEY`. If any is missing, the app stops at startup with one message listing what is missing.
- Optional: `NVIDIA_MODEL` (defaults to `openai/gpt-oss-20b`), so the LLM can be changed from `.env` without editing code.
- `DATABASE_URL` is only used by `init_db.py` (use the direct connection or session pooler, not the transaction pooler).

### 0.8 FastAPI foundation (implemented)

- `app/main.py` creates the FastAPI app (title, description, version `0.1.0`) and registers the health and repos routers.
- `GET /health` returns `{"status": "ok"}`.

### 0.9 LLM foundation (implemented)

- `app/llm/gateway.py` creates a LangChain `ChatNVIDIA` client for `openai/gpt-oss-20b` using `NVIDIA_API_KEY`.
- This is a first version only. Timeouts, retries, rate limiting and fallbacks come later.

### 0.10 Repository API foundation (partially implemented)

- `app/api/routes/repos.py` defines a `/repos` router with a `GET /repos/` handler that reads from the `repos` table through the Supabase client in `app/database.py`.
- This is a placeholder to prove the database connection. It is registered in `main.py`, but it is not yet user-scoped (see follow-ups).

### 0.11 Scope kept out of Phase 0 on purpose

Ingestion, graph analysis, retrieval, agents, verification and frontend features were deliberately not started, so the foundation stays small and correct.

### 0.12 How to run (current state)

```bash
# from the repo root, with the virtual environment active
pip install -r requirements.txt
cp .env.example .env        # then fill in real values (including DATABASE_URL)
python backend/scripts/init_db.py   # creates the tables in your Supabase project
cd backend
uvicorn app.main:app --reload
# open http://127.0.0.1:8000/health and http://127.0.0.1:8000/docs
```

Note: `init_db.py` needs an existing Supabase project (it uses `auth.users`). Only the first run applies the SQL; later runs skip files already recorded in `public.schema_migrations`.

### 0.13 Phase 0 follow-ups (found in review, fix early in Phase 1)

Dependencies and setup
- [x] `requirements.txt` contained `python==3.13.15`, which is not an installable package and breaks `pip install`. Remove it and state the Python version in the README instead.
- [x] `requirements.txt` was missing packages the code already imports: `supabase`, `langchain-nvidia-ai-endpoints`, and `uvicorn` to run the app.
- [x] `.env.example` was out of date. It lists `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GROQ_API_KEY` and others, but the code reads `SUPABASE_SECRET_KEY` and `VOYAGE_API_KEY`. Make it match `config.py`.
- [x] `.gitignore` used `.env.*`, which also ignores `.env.example`, so teammates never receive the template. Add `!.env.example`.
- [ ] Empty planned folders (`agents`, `graph`, `guardrails`, `ingestion`, `retrieval`, `verify`, `worker`, `evals`, `frontend`, `docs`) are not tracked by Git. Add a `.gitkeep` or `__init__.py` to each.
- [x] `README.md` contained pasted artifacts (a wrapping code fence and `:contentReference[...]` text). Clean these up.
- [ ] The project folder is inside OneDrive. OneDrive syncing `.git`, the virtual environment and `.env` can corrupt the repo and copies secrets to the cloud. Move the project outside OneDrive or exclude it from syncing.

Code
- [x] Register `repos_router` in `main.py`.
- [ ] `/repos` uses the secret key, which bypasses RLS, and has no authentication, so it would return every user's repositories. Replace it with a user-scoped client (verify the user's JWT, query with that context) before real data is stored.
- [x] `repos.py` used `async def` with the synchronous Supabase client, which blocks the event loop. Now a plain `def` handler.
- [x] `config.py` now checks the required variables and fails at startup with one clear message.
- [ ] `config.py` does not define the publishable key or `DATABASE_URL` mentioned in the design; add them when first needed.
- [x] The LLM model name is now read from `NVIDIA_MODEL` in configuration. Switching to HuggingFace later still needs a provider switch in the gateway.
- [ ] Add CORS middleware for the React dev server.
- [ ] Add a first smoke test (`/health`, and one LLM call).

Database
- [x] Schema committed as `db/migrations/001_initial_schema.sql`, applied by `backend/scripts/init_db.py`. Still to do: test it once on a fresh Supabase project, and confirm the enum names and values match the live database.
- [ ] Verify in Supabase that pgvector is enabled, RLS is on for every table with policies written, and the vector and full-text indexes exist.

### 0.14 Definition of done for Phase 0

- Project, team, stack and architecture decided and written down.
- Supabase project with the eight core tables created.
- FastAPI runs and serves `/health`.
- NVIDIA NIM is reachable through LangChain.
- Secrets are handled through `.env` and kept out of Git.

**Next:** Phase 1 — Codebase Ingestion and Code Intelligence: clone a GitHub repository in a worker, walk its files, and start parsing source into symbols, edges and chunks.

---