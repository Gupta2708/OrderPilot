# OrderPilot — Order Supervisor

Stage 0 foundation for the original Order Supervisor PDF assignment. The PDF is the requirements source; the existing staged prompt is preserved but is not an additional requirements source.

Implemented: Next.js/Tailwind landing page, FastAPI liveness, PostgreSQL schema/migration, local Temporal configuration, and an activity-only worker scaffold. Order workflows, AI, actions, and product controls are not implemented. **Live infrastructure and frontend validation remain blocked by host disk exhaustion; see [PROJECT_STATUS.md](PROJECT_STATUS.md).**

## Local setup (PowerShell)

Prerequisites: Node.js 24 LTS with npm, Python 3.11 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/), Docker Desktop running Linux containers, and several GB of free disk space. No API key is needed for Stage 0.

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up -d --wait
Set-Location backend
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked python -m app.checks all
uv run --locked python -m app.temporal.worker --smoke
uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

To run the scaffold worker continuously, in a third terminal from the repository root:

```powershell
Set-Location backend
uv run --locked python -m app.temporal.worker
```

The worker polls for `scaffold_health` only. It registers no order workflow and starts no runs. `--smoke` starts the actual worker briefly and shuts it down cleanly.

| Service | Local address |
| --- | --- |
| Frontend | http://127.0.0.1:3000 |
| Backend liveness | http://127.0.0.1:8000/health |
| API documentation | http://127.0.0.1:8000/docs |
| Temporal UI | http://127.0.0.1:8233 |
| Temporal gRPC | 127.0.0.1:7233 |
| PostgreSQL | 127.0.0.1:5432 |

`GET /health` returns `{"status":"ok","service":"orderpilot-api"}` and checks process liveness only. `python -m app.checks all` verifies the actual database and Temporal namespace, returning a nonzero exit code on failure. The landing page does not claim infrastructure health.

## Configuration and persistence

Backend settings load the root `.env` regardless of working directory; process environment variables override it. Compose also reads root `.env`. Defaults are local development credentials only. If you change PostgreSQL credentials or its published port, update `DATABASE_URL` to match. Initialized PostgreSQL volumes retain their original credentials.

PostgreSQL holds `supervisors`, `runs`, and `activities`. Alembic manages the schema explicitly; app startup never creates tables. JSONB holds order context, decisions, and final outputs. Order IDs and Temporal workflow IDs are each unique in runs. These database constraints do not implement workflow creation.

Temporal uses the supported development server with SQLite on a separate named volume. Its history is separate from the product database. This is a local POC configuration.

Stop infrastructure without removing data using `docker compose stop`. If startup fails, check Docker Desktop, free disk space, and availability of ports 5432, 7233, and 8233. Inspect `docker compose ps` and `docker compose logs`. Backend and frontend can start independently of infrastructure. After disk exhaustion, restart Docker Desktop before retrying; do not reset or delete existing Docker data indiscriminately.

## Validation

From `backend/`:

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked alembic upgrade head
uv run --locked alembic check
uv run --locked python -m app.checks all
uv run --locked python -m app.temporal.worker --smoke
```

After migrations succeed, enable the Postgres round-trip and uniqueness test (its data is rolled back):

```powershell
$env:RUN_INTEGRATION = '1'
uv run --locked pytest
Remove-Item Env:RUN_INTEGRATION
```

From `frontend/`:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

With both apps running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:3000 -UseBasicParsing).StatusCode
```

The interrupted frontend dependency tree was removed after disk exhaustion; `npm ci` is required before running the frontend. The lockfile preserves the successfully resolved versions. ESLint 9 is retained because the attempted version 10 update produced transitive peer warnings and was interrupted; its support warning is a known tooling limitation.

See [architecture](docs/ARCHITECTURE.md). Stage 1 will add the durable order workflow only after explicit `CONTINUE`, once Stage 0 validation is resolved.
