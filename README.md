# ask-your-data

Bring your own data (CSV / JSON / Excel / pasted text), then ask questions in plain English. The agent writes SQL, runs it safely (read-only, sandboxed to your dataset) and streams back a written answer, a table and a chart.

A learning + portfolio project: streaming SSE chat, text-to-SQL, safe SQL execution, LLM-generated chart specs, SQL caching, and a reusable "free taste, then bring your own key" gate. See [CLAUDE.md](./CLAUDE.md) for the design decisions.

## Run locally

Prerequisites: Postgres 16 and Redis (`brew install postgresql@16 redis && brew services start postgresql@16 && brew services start redis`), Python 3.11+, Bun.

```bash
createdb ask_your_data

# api  (http://localhost:8000)
cd api && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # set OPENAI_API_KEY, or FAKE_LLM=1 for offline canned answers
uvicorn main:app --reload --port 8000
pytest                      # gate, validator, ingest, executor, pipeline, API guards

# web  (http://localhost:5173)
cd web && bun install && cp .env.example .env
bun run dev
```

Click **Try the sample dataset**, then ask a question. Set `FREE_ACTIONS=1` in `api/.env` to reach the "bring your own key" state quickly. The tests use your local `ask_your_data` database (they create and remove their own throwaway datasets).

## Deploy

Web on Vercel, API + Postgres + Redis on Railway.

### Railway (api, Postgres, Redis)

1. New project -> add **Postgres** and **Redis** services, then add this repo as a service.
2. API service -> Settings -> Source -> **Root Directory = `api`**. Build and start settings come from `api/railway.toml` (Railpack, `uvicorn`, `/health` healthcheck); the Python version from `api/runtime.txt`.
3. API service -> Variables:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (private networking) |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` (private networking) |
   | `OPENAI_API_KEY` | the **dedicated demo project key** with a monthly spend limit, never your default key |
   | `OPENAI_MODEL_FAST` / `OPENAI_MODEL_SQL` | optional, default `gpt-4o-mini` / `gpt-4o` |
   | `FREE_ACTIONS`, `GATE_NAMESPACE`, `GATE_TTL_DAYS` | optional, see `api/.env.example` |

   Do **not** set `FAKE_LLM`. Leave `ENABLE_DOCS` unset so `/docs` is off.
4. Settings -> Networking -> generate a public domain; copy its URL.
5. Set a **usage limit** on the Railway project (the Hobby credit is shared with your other projects).

Notes:
- Migrations run automatically on every start (guarded by a Postgres advisory lock). The connecting DB user must be able to `CREATE ROLE` (the default Railway `postgres` user can); the migration creates the `ayd_reader` role used to run generated SQL.
- Run a **single replica**: the hourly expiry sweep runs inside the API process (it also runs once at startup).
- Use a dedicated database (or a dedicated Railway Postgres). `ayd_reader` is a cluster-level role, and each visitor dataset is a `ds_*` schema.
- Every Redis key has a TTL (drafts 30 min, SQL cache 24 h, gate counters `GATE_TTL_DAYS`), so no eviction policy is needed. If you share a Redis between demos, give each a distinct `GATE_NAMESPACE`.
- `GET /health` is liveness (used by Railway); `GET /health/ready` also pings Postgres and Redis.
- CORS is wildcard by design (`allow_credentials=False`): identity is the `X-Visitor-Id` header and the optional `X-User-Api-Key`, not cookies.

### Vercel (web)

1. Import the repo, set **Root Directory = `web`** (build/output/rewrites/security headers come from `web/vercel.json`).
2. Environment variable `VITE_API_URL` = the Railway public URL (no trailing slash), then deploy. A production build without it shows a clear error instead of calling localhost.

### Spend and abuse safety

- The OpenAI project's monthly limit is the real cost ceiling. When it is hit, visitors get the "enter your own key" prompt.
- The free-try counter is per browser (clearing site data resets it); that weakness is accepted, see CLAUDE.md.
- Guards: 5 MB upload cap checked before the body is read, 50k-row / 5-table / 50-column limits, `MAX_ACTIVE_DATASETS` shared-DB cap, 24 h dataset TTL, 5 s SQL statement timeout, 500-row result cap.

## Stack

FastAPI · React + Tailwind v4 + Recharts · Postgres · Redis · OpenAI · Vercel (web) · Railway (api, Postgres, Redis)
