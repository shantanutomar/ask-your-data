# ask-your-data — Handoff Document

Read this fully before starting implementation. All decisions from the alignment session are captured here. Do not re-litigate them; open questions are listed at the end.

---

## What and why

A "bring your own data, then ask questions" app. The user uploads or pastes data (CSV / JSON / Excel / free text), it is stored as real tables in Postgres, and the user chats with an agent that writes SQL, runs it safely, and streams back a **written answer, a table and/or a chart** depending on the question.

It is a from-scratch rebuild, for learning and as a public GitHub showcase, of the **"Ask AI"** feature Shantanu works on at his employer (a supply-chain platform). Ask AI is a streaming text-to-SQL analyst over a fixed ERP warehouse. This project keeps the architecture and concepts but replaces the fixed warehouse with **user-supplied data**, and fixes a few things the original does badly (see "Deliberate differences").

**Purpose:** learning + portfolio. Concept clarity and clean code matter more than feature richness.

**Audience:** Shantanu — full-stack engineer (React/TS/Node/Python). Has built `debate-agent` and `deep-research-agent` (FastAPI + React + SSE + raw OpenAI SDK). This project reuses those patterns and adds: schema inference/ingestion, text-to-SQL, safe SQL execution, chart specs, query caching, and a reusable usage gate.

Reference docs (outside the repo, from the employer; do not copy proprietary names/code into this repo): `LEGACY_ASK_AI_STREAMING_ARCHITECTURE.html` and `PLATFORM_V2_AGENTIC_ARCHITECTURE_GUIDE.md` in `~/Downloads`. The pipeline below is derived from them.

---

## Decisions made

### Stack
- **Backend: Python + FastAPI** — continuity with `debate-agent` / `deep-research-agent`; async-first fits SSE; pandas makes ingestion easy.
- **OpenAI Python SDK, raw** (`openai>=1.50`) — no LangChain/LlamaIndex/agent framework; the point is to understand the primitives. Put LLM calls behind a thin `llm.py` interface so another provider (e.g. Claude) can be swapped in later.
- **OpenAI models**, configured via env: `OPENAI_MODEL_FAST` (title, condense, chart spec, free-text extraction) and `OPENAI_MODEL_SQL` (text-to-SQL + analysis). Defaults `gpt-4o-mini` / `gpt-4o`; tune after benchmarking (see open questions). OpenRouter free models were tried before and were unreliable for tool/JSON output — ruled out.
- **Frontend: React + TypeScript, Bun + Vite, Tailwind CSS v4** (`@tailwindcss/vite`, `@import "tailwindcss"`, no config file), **Biome** for lint/format. **Recharts** for charts, **react-markdown** for answers.
- **Python tooling:** `ruff` (lint+format), `pytest`, `pytest-asyncio`, `fakeredis`, `httpx`.
- **Streaming:** SSE over `POST /api/chat/stream`; client uses `fetch()` + `ReadableStream` (EventSource is GET-only). Same as the other projects.
- **Database: Postgres on Railway** (user already pays the $5 Hobby plan; Railway Postgres is the default for all future projects). **SQL, not NoSQL** — questions are aggregations, text-to-SQL needs a real SQL engine.
- **Cache + gate counters: Redis on Railway.**
- **Hosting:** web → Vercel, api + Postgres + Redis → Railway.

### Data model
- **One Postgres schema per dataset** (`ds_<12 hex>`, server-generated). The user's tables live there. Metadata lives in a fixed schema `app`.
- **One active dataset per visitor.** "Reset" drops the schema, deletes conversations/messages, and invalidates cache. Uploading a new dataset replaces the old one.
- **Visitor identity:** anonymous. Frontend generates a UUID, stores it in `localStorage`, sends it as header `X-Visitor-Id`. No cookies (Vercel and Railway are different domains; cross-site cookies are unreliable, esp. Safari). No auth.
- **TTL:** datasets expire after `DATASET_TTL_HOURS` (24h) to keep the shared DB small. Lazy check on access + a background asyncio sweep (hourly) that drops expired schemas.
- **Limits** (env-configurable): 5 MB upload, 50k total rows, 5 tables, 50 columns/table, 500 result rows returned.
- **Identifiers:** table/column names are sanitized to `snake_case` (`[a-z_][a-z0-9_]*`), de-duplicated, and **always double-quoted** in generated DDL.
- **Column types** offered in preview: `text, integer, numeric, boolean, date, timestamp`.

### Metadata tables (schema `app`)
```sql
datasets(id text pk, visitor_id text, schema_name text, name text, version int default 1,
         created_at timestamptz, expires_at timestamptz)          -- unique(visitor_id)
conversations(id text pk, dataset_id text fk, title text, created_at, updated_at)
messages(id text pk, conversation_id text fk, role text, content text,
         sql jsonb, tables jsonb, chart jsonb, status text,       -- streaming|completed|cancelled|failed
         created_at timestamptz)
```
Persist user + assistant rows **before** streaming; assistant row starts `streaming` and is finalized in a `finally` (so a client abort still saves partial output as `cancelled`). Learned from the original.

### Ingestion (three paths, one result: a dataset = typed tables)
1. **File upload (CSV / JSON array / XLSX)** — main path. pandas infers types.
2. **Paste free text** — an LLM (structured output, `OPENAI_MODEL_FAST`) extracts tables `{name, columns[{name,type}], rows[]}` from arbitrary text. Counts as **1 gate action**. Input capped (~20k chars).
3. **"Load sample dataset" button** — bundled synthetic data (e.g. `customers`, `products`, `orders`, `order_items`), generated once by a script and committed as CSVs under `api/samples/`. Essential so a GitHub visitor can try the app in one click. No AI call, no gate action.

**Two-step flow with a preview (this replaces the originally proposed "fixed fields form"):**
`POST /api/datasets/preview` → returns a **draft** (tables, inferred columns/types, 5 sample rows, row counts); the parsed data is held in Redis under `draft_id` (TTL 30 min). The UI shows an editable preview (rename table/columns, change types, drop columns/tables). `POST /api/datasets/commit {draft_id, edits}` creates the schema and loads the data. Nothing is stored in Postgres before the user confirms. Free-text extraction can be wrong, so the preview is mandatory for it.

### Query pipeline (derived from Ask AI; fixed pipeline, not a free tool-calling agent)
```
POST /api/chat/stream
  1. gate.check(visitor_id, user_key)          → free | byok | blocked (blocked → error event, stop)
  2. persist user + assistant(streaming) rows; emit init
  3. new conversation? → title (FAST model), emit title
  4. history? → condense follow-up into a standalone question (FAST), include today's date
  5. cache lookup (Redis, exact match) → stored SQL or miss
  6. miss → build schema context → text-to-SQL (SQL model, JSON output)
        output: { queries:[{title, sql}], clarification_question?, answer_format: text|table|chart|mixed }
        clarification_question → stream it as the answer, STOP (no SQL runs)
  7. validate + execute SQL (read-only, see below); on error → retry text-to-SQL with the error, max 2 retries
  8. in parallel after rows exist:
        a. analysis: stream markdown answer grounded ONLY in the returned rows (SQL model)
        b. chart spec (FAST model, structured JSON) if answer_format wants a chart
  9. finalize: persist, cache the SQL (only if execution succeeded), gate.consume(), emit done
```
- **Schema context** for the SQL prompt = table/column list with types, 3 sample rows per table, and **distinct values for low-cardinality text columns** (≤ 30 distinct). This is the **Phase 1 baseline** for the original's column-value vector search (so "US" maps to the stored "United States"). High-cardinality text columns (names, IDs) only appear via sample rows, so the SQL prompt must also instruct: for free-text matching use `ILIKE '%term%'`, not `=`, unless an exact value is listed. The vector-based lookup is a **deliberate Phase 2 learning feature** (see "Phase 2"), not a fallback.
- **The model never answers from memory** — the analysis step only explains returned rows.
- Row-count/aggregation honesty: if results were truncated to `MAX_RESULT_ROWS`, say so in the table event and tell the analysis prompt.

### Safe SQL execution (this is the security boundary — build and test it first)
Replaces the original's Postgres row-level security (we have schema-per-dataset instead):
1. Parse with **`sqlglot`** (postgres dialect). Reject unless: exactly **one statement**, root is `SELECT` (CTEs allowed), no DML/DDL, no `INTO`, no locking clauses, no references to schemas other than the dataset's (reject `pg_catalog`, `information_schema`, `app`, etc.), no dangerous functions (`pg_sleep`, `pg_read_file`, `lo_*`, `set_config`, `dblink*`, `copy`). Reject on parse failure.
2. Wrap with a forced `LIMIT MAX_RESULT_ROWS + 1` (detect truncation).
3. Execute inside a transaction: `SET LOCAL ROLE ayd_reader; SET LOCAL search_path TO "<ds_schema>"; SET LOCAL statement_timeout = <ms>; SET TRANSACTION READ ONLY;`
4. `ayd_reader` is a dedicated role created once (migration) with no default privileges. On dataset commit: `GRANT USAGE ON SCHEMA`, `GRANT SELECT ON ALL TABLES IN SCHEMA` to that role for **that dataset's schema only**; revoke/drop on reset.
5. Errors are returned as `{error, input}` to drive the retry loop; never leak raw stack traces to the client.
Write adversarial tests (stacked statements, comments, `;`, quoted identifiers, `pg_catalog`, `COPY`, CTE with DML, etc.).

### Charts
- The LLM returns a **declarative chart spec**, never code:
```json
{ "type": "bar|line|area|pie|scatter", "title": "...", "table_id": "t1",
  "x": "column", "y": ["column", "..."], "series": "column|null",
  "x_label": "...", "y_label": "..." }
```
  Validate with Pydantic against the real result columns (reject unknown columns; retry once). The frontend renders it with **Recharts** using rows from the referenced table event (no data duplicated).
- The model decides between text / table / chart / mixed via `answer_format`.

### Caching (Redis)
- **Phase 1: exact-match cache of SQL, not results.** Key: `{ns}:cache:{dataset_id}:{dataset_version}:{sha256(normalized question)}` → JSON `{queries, answer_format}`, TTL 24h. Normalize = lowercase, trim, collapse whitespace. Condensed (standalone) question is what gets keyed. On hit, **re-execute** the SQL (live data) and skip the text-to-SQL call. Cache only after successful execution. `dataset_version` bumps on commit/reset, which invalidates everything.
- **Phase 2:** semantic cache — embed question, nearest-neighbour search, strict LLM judge ("Q1..Qn or NA", any doubt → NA), as in Ask AI, but self-filling per dataset. Uses the same pgvector setup as the Phase 2 column-value lookup (decided: **pgvector on Railway**, see Phase 2 section).

### The "free taste, then bring your own key" gate (standalone, reusable module)
Goal: let a visitor try a few AI actions on the owner's key, then require their own key. Must be **simple and robust**, and built as a **self-contained module that can be copied unchanged into other projects** (and ported to TS with the same tests).

- **Free actions:** `FREE_ACTIONS` (default **3**) per visitor. One action = one chat question OR one free-text ingest. File upload / sample dataset / reset / browsing are never gated.
- **Counter:** Redis key `{GATE_NAMESPACE}:gate:{visitor_id}`, `INCR` + `EXPIRE` (`GATE_TTL_DAYS`). Atomic; no reserve/settle accounting.
- **API (provider-agnostic, knows nothing about OpenAI):**
  - `check(visitor_id, user_key) -> {mode: "byok"|"free"|"blocked", remaining}` — called **before** any LLM call. `byok` if a user key is present; else `free` while count < N; else `blocked`.
  - `consume(visitor_id)` — called **only after** the AI action succeeded and mode was `free`.
- **BYOK:** user key is sent in header `X-User-Api-Key` (HTTPS). Held in browser `localStorage` with a visible "remove key" button. Server uses it for that request only; **never stores, logs or traces it** (hard rule; scrub from logs/exceptions). Validate with `POST /api/key/validate` (one cheap `models.list` call). With a user key the OpenAI client is built per request with that key.
- **Blocked UX:** clear modal/inline prompt — "You've used your free tries. Enter your own OpenAI API key to continue (it stays in your browser)". Non-AI features keep working.
- **Provider backstop:** if OpenAI returns quota/billing errors (`429 insufficient_quota`) on the server key, emit `error` with `code: "quota_exhausted"` and show the same bring-your-key prompt. The owner's dedicated OpenAI **project key** (own project, restricted models, lowest budget, prepaid credit with auto-recharge off) is the real cost ceiling. OpenAI may only offer monthly (not daily) budgets — verify in the dashboard.
- **Accepted weakness:** clearing `localStorage` resets a visitor's count. Deliberately accepted — no IP tracking, no fingerprinting, no captcha. Add Cloudflare Turnstile only if real abuse shows up.
- **Files:** `api/gate/gate.py` (~30 lines, depends only on a Redis client), `api/gate/test_gate.py` using `fakeredis` (cases: decrement, byok bypass, blocked at N, TTL expiry, concurrent requests, consume not called on failure). Frontend counterpart: `web/src/components/gate/` (key modal + remaining-tries badge). Keep these free of app-specific imports so they can be copied to other repos; the test cases are the portable spec.
- **Keys:** local dev may use Shantanu's default OpenAI key in the git-ignored `.env` (set `FREE_ACTIONS=1` to test blocked state fast, or paste the key in the UI to test BYOK). **Railway must use the dedicated project-scoped demo key, never the default key.**

### UI (Claude-like chat)
- Centered chat column, composer pinned at the bottom, left panel for the dataset (tables, columns, row counts, upload/sample/reset). Mobile-responsive (single column, dataset panel becomes a drawer).
- **Streaming indicators:** status line ("Reading schema → Writing SQL → Running query → Analysing"); blinking caret at the end of the streaming text; send button turns into a **Stop** (square) button while streaming and back on `done`; Stop aborts the fetch (`AbortController`) — the server sees the disconnect and marks the message `cancelled`.
- Assistant message layout: answer text (markdown, streamed) → table (scrollable, truncated notice) → chart → collapsible "SQL used" block. Copy button, retry/regenerate, thumbs optional (skip in phase 1).
- Remaining-free-tries badge near the composer; key modal as above.
- Reset button with confirmation dialog.

### SSE protocol
`data: {JSON}\n\n`, JSON has a `type` discriminant; mirror as a TypeScript discriminated union in `web/src/types/events.ts` (same convention as `deep-research-agent`). Helper `sse(event: dict) -> str` in the API.

| `type` | payload | UI effect |
|---|---|---|
| `init` | `conversation_id`, `message_id` | set ids |
| `status` | `step`: `reading_schema \| writing_sql \| running_query \| analysing` | status line |
| `title` | `title` | sidebar/header title (new chats) |
| `sql` | `queries[{title, sql}]`, `cache_hit: bool` | collapsible SQL block |
| `table` | `table_id`, `title`, `columns[]`, `rows[][]`, `truncated: bool` | table |
| `chart` | `spec` (see Charts) | chart |
| `analysis_token` | `token` | append to markdown |
| `error` | `code` (`blocked \| quota_exhausted \| bad_sql \| internal ...`), `message` | toast / key prompt |
| `done` | `gate: {mode, remaining}` | stop streaming state, update badge |

---

## Explicitly ruled out (do not revisit)

- **`exec()` of LLM-written Python for charts** (what the original does) — security risk; declarative chart spec instead.
- **Postgres row-level security / tenant roles per access level** — overkill; schema-per-dataset + read-only role + sqlglot validation instead.
- **LangChain / LlamaIndex / agent frameworks** — raw SDK only.
- **LiteLLM proxy, Langfuse, Mage ETL, MongoDB, Atlas vector search, Qdrant, mem0** — employer infra, unnecessary here. (Langfuse-style tracing can be a later nice-to-have.)
- **Plotly** — heavy bundle; Recharts is enough. (Vega-Lite was the alternative if chart flexibility is needed later.)
- **NoSQL for user data** — wrong tool for aggregation Q&A.
- **WebSockets** — SSE is sufficient.
- **IP-based limiting, fingerprinting, captcha (for now), daily-cost accounting in code, reserve/settle token accounting** — gate is deliberately just a per-visitor counter + provider-side cap.
- **Cookies for visitor identity** — cross-domain issues.
- **Authentication / accounts** — anonymous visitor ID only.
- **OpenRouter free models** — unreliable for structured output here.
- **Docker, CI/CD** — not needed (Railway/Vercel deploy from git). Local Postgres + Redis via Homebrew.
- **Separate repo/package for the gate right now** — keep it as an isolated folder; extract later if wanted.

---

## Architecture / folder structure

```
ask-your-data/
├── CLAUDE.md  README.md  .gitignore
├── api/                          ← FastAPI (Railway root directory = api)
│   ├── main.py                   ← app, CORS, routers, startup (pool, redis, sweep task), /health
│   ├── config.py                 ← env → typed settings
│   ├── requirements.txt  runtime.txt  railway.toml  .env.example
│   ├── db/                       ← pool, migrations (SQL files), meta repo (datasets/conversations/messages)
│   ├── ingest/                   ← parsers (csv/json/xlsx), type inference, free-text extractor, draft store (Redis), commit (DDL + bulk load)
│   ├── sql/                      ← validator (sqlglot), executor (read-only tx), schema_context builder
│   ├── pipeline/                 ← orchestrator (async generator → events), condense, text_to_sql, analysis, chart_spec, cache
│   ├── llm.py                    ← thin OpenAI wrapper (per-request client, JSON/structured output, streaming, usage logging)
│   ├── gate/                     ← STANDALONE: gate.py + test_gate.py (no app imports)
│   ├── routers/                  ← datasets.py, chat.py, conversations.py, key.py
│   ├── samples/                  ← sample CSVs + generator script
│   └── tests/
└── web/                          ← React + Vite (Vercel root directory = web)
    └── src/
        ├── types/events.ts       ← SSE discriminated union
        ├── hooks/useChatStream.ts  ← fetch + ReadableStream parser, abort
        ├── components/chat/ dataset/ upload/ gate/ charts/
        ├── lib/visitor.ts  lib/api.ts
        └── ...
```
Orchestrator is an **async generator yielding event dicts**; the router wraps it in `StreamingResponse(media_type="text/event-stream")`. Each step is a small, separately testable function.

---

## Mocked / temporary

- Nothing mocked: real LLM, real DB. For development, a `FAKE_LLM=1` toggle returning canned JSON is **optional** (useful for tests/CI-less local runs); not required.
- Sample dataset is synthetic data generated by a script.

---

## Implementation backlog (in order)

0. **Scaffold** — `api/` (venv, requirements, `main.py` with `/health`, CORS, config) and `web/` (Bun + Vite + React + TS + Tailwind v4 + Biome). Local Postgres + Redis via Homebrew; verify connectivity.
1. **DB layer** — migrations for `app` schema + `ayd_reader` role; meta repo; create/drop dataset schema; TTL sweep.
2. **Safe SQL executor + validator + adversarial tests** (do this before any LLM work).
3. **Gate module + tests** (`fakeredis`), then `key.py` router (`/api/key/validate`).
4. **Ingestion** — CSV/JSON/XLSX parsers, type inference, preview/commit endpoints, sample dataset + generator, limits.
5. **LLM wrapper + non-streaming pipeline** — schema context → text-to-SQL → execute → retry; test via pytest against the sample dataset; log token usage per step (this produces the free-tier benchmark).
6. **Streaming** — orchestrator generator, SSE endpoint, analysis streaming, chart spec + validation, persistence with `finally` finalization, cancel handling.
7. **Exact-match cache** (Redis) + condense step for follow-ups.
8. **Frontend** — events types, `useChatStream`, layout, dataset panel + upload + editable preview, chat UI (stream caret, status, stop), table + chart renderers, SQL block, gate modal + badge, reset.
9. **Free-text ingest** (LLM extraction → same preview flow).
10. **Deployment** (below), then README polish with screenshots/GIF.

## Phase 2 — vector search (deliberate learning goal; do NOT build in Phase 1)

Phase 1 ships and works first with the simple baseline. Phase 2 exists to learn embeddings + vector search properly, and to **measure** them against the baseline. Both features share one setup, so build them in this order:

**P2.0 Infra:** pgvector on Railway. The default Railway Postgres image does not include it, so deploy Railway's pgvector Postgres template/image (or switch the Postgres service image) and `CREATE EXTENSION vector`. Local: `brew install pgvector`. Embeddings: `text-embedding-3-small` (1536 dims) via the OpenAI SDK (OpenRouter does not proxy embeddings). Verify current model name before wiring.

**P2.1 Column-value vector lookup** (the original's technique):
1. At dataset commit, for text columns with > 30 distinct values (cap ~5k distinct values per column, ~50k per dataset), embed the distinct values in batches and store in `app.column_values(dataset_id, table_name, column_name, value, embedding vector(1536))` with an HNSW/ivfflat index. Drop rows on reset/expiry.
2. At question time (cache miss only): FAST model extracts keywords → embed keywords + the full question → top-5 nearest per keyword, filtered by `dataset_id` → de-duplicate → inject as hints `table.column = 'exact stored value'` into the text-to-SQL prompt.
3. Embedding calls use the visitor's key if supplied, else the server key **without consuming a free action** (cost is pennies); enforce the value caps above.

**P2.2 Eval harness (the real learning):** a script + a fixed question set (15–20 questions where exact spelling/wording matters, e.g. "laptops" vs "Notebook Computers", "acme" vs "ACME INC.", "US" vs "United States") run against the sample dataset (and a deliberately messy one). Compare three strategies on accuracy (does the SQL return the expected rows?), latency and token cost:
   - A. Baseline: sample rows + distinct values + `ILIKE` rule
   - B. Fuzzy text: `pg_trgm` similarity lookup
   - C. Vector lookup (P2.1)
   Write the findings in the README ("when is each worth it") — this comparison is the showcase.

**P2.3 Semantic question cache:** embed the standalone question → nearest-neighbour over past cached questions for the same dataset/version → strict LLM judge picks a hit or `NA` (any doubt, or a different number/date/entity → `NA`) → reuse stored SQL and re-execute. Table `app.question_cache(dataset_id, dataset_version, question, queries jsonb, embedding)`.

**Other Phase 2 / later items:** conversation history sidebar, regenerate/siblings, Turnstile if abused, optional Claude provider + provider dropdown for BYOK, table "summarise" action, export results to CSV.

---

## Implementation status (Phase 1 built; not yet run against real OpenAI)

All backlog steps 0-10 are implemented. Verified: 112 pytest tests pass (validator adversarial cases,
read-only executor + role isolation against real local Postgres, gate, ingest, full pipeline with a
stub LLM incl. retry/cache/clarification/cancel), `ruff` clean, `bun run build` + Biome clean, and a
browser run of the whole UI against `FAKE_LLM=1` (sample load, streaming, chart, restore on reload,
blocked flow + key modal, mobile layout). **Not verified:** real OpenAI calls (structured outputs via
`chat.completions.parse`, streaming usage), file upload through the browser UI, free-text extraction,
Railway/Vercel deploy. Next: set `OPENAI_API_KEY`, run the question benchmark (open question 1).

Deviations / additions vs. this document:
- `app.datasets` has an extra `tables jsonb` column: per-table summary (columns, row count, 3 sample rows,
  distinct values for text columns <= 30, min/max for numeric/date columns) computed once at commit and used
  both for the schema prompt and the dataset panel (no per-question introspection queries).
- Validator also requires unqualified tables to be dataset tables or CTE names (blocks implicit
  `pg_catalog` lookups like `FROM pg_class`); executor runs the sqlglot-*regenerated* SQL, not the raw text.
- `sql` SSE event also carries `answer_format`; `table` events are only emitted for non-`text` formats.
- Extra endpoints: `GET /api/gate` (badge), `GET /api/datasets/current`, `POST /api/datasets/sample`,
  `POST /api/datasets/preview-text`, `GET/DELETE /api/conversations...` (UI restores the latest conversation).
- `FAKE_LLM=1` (api/fake_llm.py): offline canned LLM for UI work; unset for real answers.
- Web scripts run via `bunx --bun` because the local `node` binary on this machine has the wrong CPU arch.
- Local Python is 3.13 (runtime.txt pins 3.11.9 for Railway); `requirements-dev.txt` adds test/lint deps.
- Production hardening: pinned deps; `runtime.txt` is 3.13.0 (the version actually tested, not 3.11.9);
  `BodyLimitMiddleware` (Content-Length caps), `MAX_ACTIVE_DATASETS` cap (503), startup + hourly expiry
  sweep, `ENABLE_DOCS` (off by default), `/health/ready`, Redis health checks, Vercel security headers,
  React error boundary, `VITE_API_URL` required in production builds. See README "Deploy".
- Not built (still backlog/Phase 2): conversation sidebar, regenerate siblings, Turnstile, vector search.

---

## Dev commands (confirmed)

```bash
# one-time: local services (no Docker)
brew install postgresql@16 redis && brew services start postgresql@16 && brew services start redis
createdb ask_your_data

# api
cd api && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill OPENAI_API_KEY (or set FAKE_LLM=1 for offline canned answers)
uvicorn main:app --reload --port 8000
pytest                          # unit tests (gate, validator, ingest)
ruff check . && ruff format .

# web
cd web && bun install && cp .env.example .env
bun run dev                     # http://localhost:5173
bun run format                  # biome check --write
bun run build                   # tsc + vite build
```
Planned `requirements.txt`: `fastapi, uvicorn[standard], openai>=1.50, asyncpg, redis>=5, pandas, openpyxl, sqlglot, pydantic>=2, python-multipart, python-dotenv`; dev: `pytest, pytest-asyncio, fakeredis, httpx, ruff`.

---

## Deployment (files created during Phase 1 implementation, step 10 — contents ready to copy)

CORS (settled convention — wildcard, auth is not cookie-based so this is safe; `allow_credentials=False` is required with `*`):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],   # must include X-Visitor-Id and X-User-Api-Key
)
```

**`web/vercel.json`**
```json
{
  "buildCommand": "bun run build",
  "outputDirectory": "dist",
  "installCommand": "bun install",
  "framework": "vite",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

**`api/railway.toml`**
```toml
[build]
builder = "RAILPACK"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

**`api/runtime.txt`**
```
python-3.11.9
```

**Railway dashboard (manual):**
- New project: add **Postgres** and **Redis** services + the `api` service from this repo. API → Settings → Source → Root Directory = `api`.
- API variables: `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `REDIS_URL=${{Redis.REDIS_URL}}` (use private networking URLs), `OPENAI_API_KEY` = **dedicated project key**, plus the gate/limit vars from `api/.env.example`.
- Set a **usage limit** on the Railway account/project (the $5 Hobby credit is shared across all of Shantanu's Railway projects, e.g. medi-guide). Rough expectation: small API ≈ $1–3/mo, small Postgres ≈ $1–3/mo, Redis ≈ <$1–2/mo — verify on railway.com/pricing.
- Consider reusing an existing Railway Postgres/Redis (separate database / key prefix) to save credit — see open questions.

**Vercel dashboard:** env `VITE_API_URL` = Railway API public URL (set after first deploy).

---

## Open questions (decide during implementation)

1. **Model choice + benchmark:** log tokens/cost per step on the sample dataset with 15–20 representative questions; then set `OPENAI_MODEL_SQL` / `OPENAI_MODEL_FAST` and confirm `FREE_ACTIONS=3` is affordable. Verify current OpenAI model names before wiring defaults.
2. **Railway Postgres/Redis:** dedicated instances for this app, or reuse existing ones with a separate database / key prefix (cheaper)?
3. **Phase 2 vector store:** decided — pgvector on Railway (not ChromaDB). Open only: exact Railway pgvector template vs custom image, and HNSW vs ivfflat index.
4. **OpenAI spend cap:** confirm what the dashboard offers (monthly vs daily budget, prepaid balance behavior).
5. **Chart library:** Recharts assumed; switch to Vega-Lite only if chart variety becomes a limitation.
6. **Extract the gate** into its own repo/package once a second project needs it (then port to TypeScript for the Bun projects using the same test cases).
7. **Unrelated mid-chat question:** original passes old SQL history to text-to-SQL, which may bias it; decide whether to drop history when condense returns the question unchanged.

---

## Conventions

- Python: type hints everywhere, `ruff`, small pure functions, async I/O, Pydantic models for LLM structured outputs and request bodies. Events are plain dicts with a `type` field.
- TypeScript strict mode; Biome; SSE events mirrored as a discriminated union; no `any`.
- Folder names kebab-case; Python modules snake_case; React components PascalCase.
- Never log or persist user API keys, request headers wholesale, or full prompts containing user data in production logs.
- Every LLM step: one prompt file/function, JSON/structured output where output is machine-consumed, token usage logged.
- Tests colocated or under `api/tests/`; the SQL validator and the gate are the two must-be-well-tested modules.
- Do not make git commits unless the developer asks.
