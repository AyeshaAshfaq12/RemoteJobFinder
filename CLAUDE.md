# Remote Job Finder

MCP connector + in-chat views (MCP Apps) + small companion web app. The user's own Claude
crawls the web for remote jobs and does all reasoning; our server dedupes, scores ghost risk,
compiles CVs, and tracks applications. Full specs: `docs/` (Build Spec wins over Product Spec).
Build milestone by milestone (Build Spec §13); each ends with tests green and its gate checked.

## Hard rules (never break)
- No paid/third-party data APIs and **no LLM API calls** from our server. Only outside services:
  payment provider (merchant of record) and an email sender for sign-in codes.
- No scraping behind logins. No LinkedIn/Indeed crawling from our server. Respect robots.txt.
- No fabricated CV content. Server-side CV validation (Build Spec §8) is mandatory.
- Every personal row is scoped by `user_id`. No query reads personal data without it.

## Ask the human before
- Adding a dependency not named in the spec or in the approved list below.
- Changing a public MCP tool schema.
- Changing the DDL (migration 001 = Build Spec §4 + OAuth tables).
- Any spec ambiguity: ask, don't assume.

Approved extra deps: asyncpg, psycopg, httpx, boto3, cryptography, webauthn, prometheus-client,
pytest-asyncio, pytest-cov, @testing-library/*, @axe-core/playwright, @storybook/react-vite,
typescript-eslint.

## Principles
Chat-native first (views speed things up, never gate) · Evidence over vibes (every score shows
reasons + sources) · One decision per view · Honest by design · Calm, not a feed (10–25 jobs/day)
· Fast (first paint ≤300 ms after tool result, interactions ≤100 ms, optimistic) · Accessible
(WCAG 2.2 AA, keyboard, 360 px, host light/dark theme).

## Stack
- Backend: Python 3.12, FastAPI + official MCP Python SDK (Streamable HTTP, stateless) at `/mcp`,
  Postgres 16 + SQLAlchemy 2 async + Alembic, Celery + Redis (beat), OAuth 2.1 via the MCP SDK auth server (`mcp.server.auth`, our Postgres provider; replaces Authlib — decided 2026-10-29),
  Tectonic (sandboxed subprocess), S3-compatible storage, structlog, Prometheus.
- Frontend: pnpm workspace, TypeScript strict. `packages/ui` (tokens + Radix + Tailwind),
  `packages/views` (React + Vite + `@modelcontextprotocol/ext-apps`, one self-contained HTML per
  view → `dist/<view>.html`, served as `ui://` resources), `apps/web` (Next.js App Router).
- Plugin: `plugin/` (skills: daily-scan, fit-rubric, ghost-rubric, cv-writer; commands: jobs,
  apply, tracker, profile).

## Commands
```sh
docker compose up                  # postgres, redis, api, worker, beat, web
# backend (cd backend)
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest                      # unit; integration needs Docker (testcontainers)
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# frontend (cd frontend)
pnpm install
pnpm -r lint && pnpm -r typecheck && pnpm -r test
pnpm --filter @rjf/views build
```

## Conventions
- Python: uv, ruff (lint + format), `mypy --strict`, pytest. TS: strict, ESLint, Vitest, Playwright.
- Migrations only through Alembic. Settings only via env vars (pydantic-settings); never hard-code secrets.
- Pin latest stable versions in lockfiles (`uv.lock`, `pnpm-lock.yaml`).
- Tool descriptions are 1–3 sentences (what + when); review them like code.
- Logs: structlog JSON with request id + tool name; never personal content. audit_log stores counts only.

## Definition of done
Tests pass, ≥85% coverage on new code · lint/format/type clean · tool/API docs updated ·
UI checked light + dark at 360 px · no new MCP Inspector warnings for changed tools.
