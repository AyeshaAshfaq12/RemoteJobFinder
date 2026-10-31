# Remote Job Finder — Remaining Work & Full Requirements

Handoff for the next Claude Code session (written 2026-10-31). The source specs are the two PDFs
in `docs/` ("Product Spec" and "Build Spec for Claude Code", both Oct 20, 2026). Everything still
needed from them is summarised below; where the two PDFs differ, the Build Spec wins. Read `CLAUDE.md` first, then this file.

**Working rule from the user: if anything is ambiguous, ask the user directly. Do not
assume.** Also ask before adding a dependency, changing a public MCP tool schema, or changing
the DDL.

---

## 0. Decisions already made (do not re-ask)

| Topic | Decision |
|---|---|
| Milestones | Work M0→M6 continuously. Pause only at gates that need the human (staging, a real profile, beta users). |
| Repo | `github.com/AyeshaAshfaq12/RemoteJobFinder` (public). The spec PDFs are in `docs/` (pushed 2026-10-31, user's choice). |
| Extra deps approved | asyncpg, psycopg, httpx, boto3, cryptography, webauthn, prometheus-client, pytest-asyncio, pytest-cov, @testing-library/*, @axe-core/playwright, @storybook/react-vite, typescript-eslint. Ask before any other. |
| TypeScript | Pinned to `~6.0.x`, because typescript-eslint doesn't support TS 7. |
| OAuth server | MCP Python SDK built-in auth server (`mcp.server.auth`) with our Postgres provider (`app/auth/provider.py`). Authlib was dropped: it has no Starlette authorization server. |
| Migration 001 | Section 4 DDL plus OAuth tables (`oauth_clients`, `oauth_authorization_codes`, `oauth_tokens`; codes and tokens stored hashed; refresh `family_id`). `profiles.status` also allows `'superseded'` (approved). |
| Eligibility golden data | Claude drafted 150 cases plus the region map. **The user still has to review them.** |
| Region map | UN M49 where one exists, otherwise the usual hiring meaning. PK is **in** APAC, Asia and South Asia; **not in** EMEA, MENA, Middle East or Europe. Cyprus counts as Europe. |
| Salary | Store the original min/max/currency/period. Convert to USD/month only when comparing with `salary_floor_usd_month` or displaying. FX table in `app/discovery/fx_rates.json`: approximate seed values the user must confirm and update monthly. |
| Timezone | "EST/PST hours" with no number = 8 h. A timezone mismatch is a soft signal only (`tz_conflict` flag) and never hides a job. |
| Restricted jobs | Store the restricted country set in `allowed_countries`. A user in that country is eligible. |
| Reposts | `repost_count_90d = (history rows for company+title_norm in 90d − 1) + (same-hash sighting gaps > 21 days within 90d)`. Every new job is written to `job_postings_history`. |
| Seniority | `principal` → `lead`. |
| Staging gate | Use a temporary public tunnel (e.g. cloudflared) for the claude.ai connector check. Real hosting comes later. |
| Email codes | Generic SMTP via env vars. With no SMTP host, log the code to the console (local/test only). |
| Web + API | ONE public domain, path-routed: `/api`, `/mcp`, `/authorize`, `/token`, `/register`, `/revoke`, `/.well-known/*` go to FastAPI; everything else goes to Next.js. The session cookie is shared. Sign-in, consent and profile-review pages live in Next.js. |
| update_profile input | The complete proposed `MasterProfile`, plus optional `preferences` and `change_note`. The server diffs it against the active version. |
| search_jobs | Returns the **full** `jd_text` (no truncation). |
| Profile approval fallback | When the host can't render the view, `update_profile` text gives a link to `<origin>/profile/review?version=N`, where the user approves on the web. There is no model-facing approve tool. |

---

## 1. What exists today (commit `e0819fb`)

- **M0 scaffold:**
  - repo layout and `CLAUDE.md`
  - `docker-compose.yml` (postgres, redis, migrate, api, worker, beat, web)
  - backend and frontend Dockerfiles
  - CI workflow (`.github/workflows/ci.yml`)
  - pnpm workspace: `packages/ui` (tokens.css + `ghostBand`), `packages/views` (placeholder), `apps/web` (placeholder landing)
  - plugin skills and commands (`plugin/skills/*`, `plugin/commands/*`)
- **M1 discovery core:** all done and tested.
  - migration 001
  - normalize, company match, dedupe, eligibility (150/150 golden cases), salary parsing, ghost scoring (20 fixtures)
  - idempotent ingest (`app/discovery/ingest.py`)
- **M2 backend:**
  - OAuth provider; email-code sign-in and sessions (Redis)
  - encrypted, versioned profiles with diff and partial acceptance
  - all 14 tools in `app/mcp/tools/`
  - MCP Apps `ui://` resources (placeholders until M5)
  - REST endpoints `app/api/auth.py` and `app/api/profile.py`
  - integration tests: full journey, scopes, refresh rotation, cross-user isolation, web fallback
  - `generate_cv` and `ui_get_cv_pdf_url` are **placeholders** that return the error code `unavailable`.

---

## 2. Remaining tasks

### 2.1 Verify current state first
- [ ] `docker compose up --build`: all services start and `GET /healthz` returns 200 (M0 gate).
- [ ] `cd backend && uv sync && uv run pytest`: all unit and integration tests pass. In particular, re-run `tests/integration/test_mcp_tools.py`: `test_partial_profile_acceptance` was fixed but not re-run, and `test_web_profile_review_fallback` has not passed yet.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy`: clean. These have not been run on the M2 code.
- [ ] Frontend: `pnpm install && pnpm lint && pnpm typecheck && pnpm test && pnpm build`.
- [ ] GitHub Actions CI is green.

### 2.2 Finish M2 — MCP server and OAuth
- [ ] Unit tests for `app/security/crypto.py`, `app/auth/pending.py`, `app/profiles/diff.py` and `app/auth/web.py`. Coverage of new code must be 85% or more.
- [ ] Next.js pages in `apps/web`:
  - `/signin`: passkey first, 6-digit email code as the fallback. Calls `POST /api/auth/email/start` and `/api/auth/email/verify`.
  - `/consent?req=…`: `GET /api/oauth/request` shows the client name, the redirect host and the scopes in plain language, with a link to the privacy policy. Approve/Deny calls `POST /api/oauth/decision`, then follows `redirect_to`. The user must be signed in first.
  - `/profile/review?version=N`: git-style diff. Uses `GET /api/profile/proposal/{v}` and `POST /api/profile/proposal/{v}/resolve` with `{decision, rejected_change_ids}`.
- [ ] One-domain routing: Next.js `rewrites` (or a reverse proxy) sends `/api/*`, `/mcp`, `/authorize`, `/token`, `/register`, `/revoke` and `/.well-known/*` to the API.
- [ ] Passkeys (WebAuthn, using the `webauthn` lib):
  - registration and login endpoints
  - a credentials table (DDL change: ask first)
  - passkeys are the primary sign-in method
  - email codes stay as the fallback (10-minute expiry, 5 attempts)
  - sessions: HTTP-only, Secure, SameSite=Lax cookies
- [ ] Add to `docker-compose.yml` and `backend/.env.example`: `RJF_PUBLIC_ORIGIN`, `RJF_SECRET_KEY`, `RJF_PROFILE_KEYS` (format `1:<base64 32 bytes>`, newest first), `RJF_SMTP_*`, `RJF_EXTRA_ALLOWED_HOSTS`.
- [ ] Logging and request limits:
  - structlog JSON with a request id and tool name; never personal content
  - a 2 MB request body limit on the REST API (only `/mcp` has one now)
- [ ] Prometheus `/metrics`: tool latency p50/p95, tool error rate by code, CV compile time, jobs submitted per day, dedupe rate, share of eligible jobs.
- [ ] Free-plan limits, enforced inside the tools: **1 scan a day** (count `submit_jobs` or `search_jobs` per day; ask which), **3 CVs a month** (`users.cv_quota_used`), 30-day job history. Pro: unlimited scans and CVs, full history, the Insights screen. Error code: `quota_exceeded`.
- [ ] Tool and API docs, e.g. `docs/tools.md`.
- [ ] MCP Inspector (CLI): every tool lists with a valid schema, `ui://` resources resolve with MIME `text/html;profile=mcp-app`, and there are no warnings. Add this to CI.
- [ ] **M2 gate:**
  - [ ] OAuth 2.1 + PKCE + DCR work, and the metadata endpoints are served.
  - [ ] All 10 model-facing tools are valid in MCP Inspector.
  - [ ] Over a public tunnel, add the connector in claude.ai as a custom connector, sign in, and confirm `get_profile` succeeds.
  - [ ] Cross-user tests pass.

### 2.3 M3 — Plugin and first real scan
- [ ] `plugin/.claude-plugin/plugin.json`: name `remote-job-finder`, a description, a version, and the MCP server URL, so installing the plugin also offers the connector. Ask the user for the URL.
- [ ] Onboarding copy tells the user to create a daily scheduled task in Claude with the prompt "Run my daily job scan". Our server can't create it.
- [ ] **M3 gate (needs the human):**
  - [ ] The plugin installs and `/jobs` runs daily-scan end to end.
  - [ ] With Abdullah's real profile, one scan stays within its fetch budget, submits 20 or more jobs, and saves scores.
  - [ ] Of the jobs shown as Low ghost risk, a manual check finds at least 90% live on the company's own site.
  - [ ] A daily scheduled task runs the scan unattended 3 days in a row.

### 2.4 M4 — CV engine (`app/cv/`)
Claude never sends raw LaTeX. It sends `CvContent` (in `app/cv/schema.py`, already written) that points at Master Profile bullet ids.

- [ ] **`validate.py`.** Any failure rejects the request with `validation_failed` and a list of exact problems Claude can fix.
  1. Every `ref_id` and `source_bullet_id` exists in the active profile version.
  2. Every skill in `skills` is in `profile.skills` (case-insensitive, with an alias map, e.g. postgres = postgresql).
  3. Every number or percentage in a rewritten bullet appears in its source bullet's `text` or `metrics`.
  4. Capitalized tech terms in a rewritten bullet, matched against a list of about 2,000 known technologies, appear in the source bullet's text or skills.
  5. The summary uses only numbers found in `summary_facts` or in some bullet's `metrics`.
  6. Employers, titles and dates are never in CvContent. The renderer takes them from the profile.
  7. The PDF fits 2 pages at most. The compile step counts pages; if there are too many it returns `too_long` with the overflow in lines.
  - The cover note goes through the same numbers check (rule 3).
- [ ] **`render.py`:** Jinja2 with LaTeX-safe delimiters (`\VAR{}`, `\BLOCK{}`). Every value goes through `latex_escape()`, which escapes `& % $ # _ { } ~ ^ \`.
- [ ] **Templates** `cv/templates/{classic,modern,compact}.tex.j2`: standard packages only; ATS-friendly (single column, real text, standard section names).
- [ ] **`compile.py`:**
  - `tectonic -X compile --untrusted --outdir <tmp>` in a subprocess
  - 20-second timeout, no network, 512 MB memory limit, temp directory deleted afterward
  - the API image includes the Tectonic binary with its package cache pre-warmed at build time
  - target compile time under 8 s
- [ ] **Storage:** upload `cv.tex` and `cv.pdf` to S3-compatible storage under `users/<user_id>/cvs/<cv_id>/`. The view gets a signed URL valid for 10 minutes (`ui_get_cv_pdf_url`). Ask which provider, and whether to use MinIO locally.
- [ ] **`generate_cv` tool:**
  - input `{job_id, template: classic|modern|compact, content: CvContent, kit}`
  - validate, insert a `cvs` row with status `queued`, enqueue a Celery compile, and return immediately with `status: queued`
  - the view polls until the PDF is ready
  - checks the quota and the rate limit (10/hour)
- [ ] **Kit:** `{cover_note ≤180 words, screening_answers: [{question, answer}], recruiter_dm ≤300 chars, gap_report: [{requirement, honest_framing}]}`, stored in `cvs.kit`.
- [ ] **Tests:**
  - each template compiles
  - a 2-page-limit fixture
  - injection strings (`\input{/etc/passwd}`) come out escaped
  - all 7 validation rules
- [ ] **M4 gate:**
  - [ ] All 3 templates compile in under 8 s at p95 and fit 2 pages.
  - [ ] A fabricated number or skill is rejected with a precise message.
  - [ ] `/apply` produces a PDF, a `.tex` file and a full kit for 5 real jobs, each reviewed by a human as truthful.

### 2.5 M5 — Design system and in-chat views
**Design language "Briefing":** calm, dense with evidence, and fast. Its signature details:
- the sightings timeline
- provenance hover in the CV studio
- evidence chips on every claim

**Tokens** (`packages/ui/src/tokens.css`, already written):
- **Color:** 11-step neutral gray; accent indigo-600 (light) / indigo-400 (dark); green good, amber warn, red risk. Semantic colors are never the only signal; always pair them with an icon and a label.
- **Contrast:** body text 7:1, secondary text 4.5:1.
- **Type:** system UI stack in views, Inter variable on the web. `tabular-nums` for data. Scale 12/13/14/16/20/28 px, line height 1.45.
- **Space:** 4 px grid; component padding 12/16; section gap 24.
- **Shape:** radius 10 (cards), 6 (chips), 999 (pills); 1 px hairline borders; no shadows in chat views.
- **Motion:** 120 ms ease-out for hover/press, 180 ms for panels, a spring (stiffness 400, damping 30) for drag. All motion is instant under `prefers-reduced-motion`.
- **Icons:** Lucide, 16 px, stroke 1.75.

**Components** (Radix primitives + Tailwind; each has a Storybook story in both themes): JobCard, FitBadge, GhostMeter (3-segment bar + band label + reasons popover), EvidenceChip (favicon + domain, opens the source), SightingsTimeline, RequirementList, PdfPreview, KanbanBoard, DiffRow, Skeleton, EmptyState, Toast.

**View runtime rules:**
- Each view is ONE self-contained HTML file in `frontend/packages/views/dist/<view>.html`, 150 KB gzipped or less (alias React to preact/compat if needed). The backend already loads these files at startup.
- Use `@modelcontextprotocol/ext-apps`.
- Read data from `structuredContent`, and call view-only tools through the SDK.
- Report content height to the host and never show an inner scrollbar.
- Map the host's theme variables onto our tokens; otherwise follow `prefers-color-scheme`.
- Offer fullscreen for the shortlist, CV studio and tracker.
- Updates are optimistic, with a rollback toast on failure.
- Everything is reachable by Tab; arrow keys move within lists and boards.
- Strict CSP; no third-party requests.
- First paint within 300 ms of the tool result; interactions respond within 100 ms.

**Views:**
- [ ] **Shortlist** (`save_job_scores`), answering "which jobs today?":
  - Header: "14 new · 4 Match · 6 Stretch", the date, and a filter segmented control (All/Match/Stretch/Reach). A quiet "N hidden as likely ghost jobs" link opens the hidden list.
  - Cards sorted by band, then ghost score ascending, then recency. Each card shows the title, company with favicon, eligibility pill ("Worldwide", "EMEA incl. PK"), salary if listed, FitBadge, GhostMeter and a one-line fit summary.
  - Enter/click opens job detail (calls `get_job` via the host). `D` dismisses (`ui_dismiss_job`) with an undo toast. `A` sends the follow-up message "Apply to <job>".
  - States: a skeleton of 5 cards while loading; empty state "No new matches today — 37 jobs checked, 0 eligible" plus the top reason.
- [ ] **Job detail** (`get_job`), answering "is this real, and do I fit?":
  - Two columns on desktop, stacked on mobile.
  - Left: the JD, with must-haves highlighted inline (green when met, amber when a gap).
  - Right, three panels:
    - Fit: RequirementList, with the evidence bullet on hover.
    - "Is it real?": GhostMeter plus every reason row (e.g. "+35 Not on company ATS") with an EvidenceChip.
    - History: SightingsTimeline. A 90-day axis; each sighting is a dot colored by source kind; each repost is a hollow diamond with a dashed connector to the earlier posting; hovering shows the date, source and URL.
  - Actions: primary "Build my CV for this" (sends a message); secondary "Save" and "Not for me".
- [ ] **CV studio** (`generate_cv`), answering "is this CV right and honest?":
  - Split layout: JD must-haves checklist on the left, live PDF preview (`ui_get_cv_pdf_url`) on the right.
  - Provenance hover: hovering a CV bullet in the text outline highlights the requirement it answers and shows the original profile bullet with changed words marked.
  - Gap report panel, plus tabs for the cover note, screening answers and recruiter DM, each with a plain-text copy button.
  - Actions: Download PDF, Download .tex, Switch template (sends a message to regenerate), Mark as applied (`track_application`).
  - States: a compiling shimmer over a skeleton page. On failure, show the exact problems plus an "Ask Claude to fix" button that sends them as a message.
- [ ] **Tracker** (`list_applications`), answering "where do I stand?":
  - Kanban: Saved → Applying → Applied → Interviewing → Offer, plus a collapsed Closed column (rejected/withdrawn/ghosted).
  - Dragging a card calls `ui_set_application_status`. Keyboard: Space picks a card up, arrow keys move it.
  - An amber "Follow up" badge appears when `follow_up_at` is today or earlier. The header shows "N follow-ups due".
  - Cards show days since applying and the ghost band at the time of applying.
- [ ] **Profile review** (`update_profile`), answering "is this what I want saved?":
  - A git-style diff grouped by role/project: additions green, removals red, edits word by word.
  - Accept or reject each change, or accept all, via `ui_resolve_profile_change` with `rejected_change_ids` (the change ids come from `app/profiles/diff.py`).
  - Nothing becomes active until approved.
- [ ] **Text fallbacks:** each tool's text content reads well in hosts without UI support.
- [ ] **Tests:**
  - Vitest + Testing Library: each view renders from fixture `structuredContent`
  - Playwright with a mock host: keyboard paths
  - axe scan with zero violations
  - visual snapshots in light/dark at 360/768/1280 px
- [ ] **M5 gate:**
  - [ ] Stories exist in both themes.
  - [ ] All 5 views render in Claude from real tool results, including the timeline and provenance hover.
  - [ ] Zero axe violations, and full keyboard paths work.
  - [ ] Each view is 150 KB gzipped or less.
  - [ ] Text fallbacks read well.

### 2.6 M6 — Web app, billing, beta
**Screens** (`apps/web`, Next.js App Router, Inter variable font):
- [ ] **Landing:** one-line promise; a looping 20-second product video (shortlist → job detail → CV studio); 3 proof points (ghost filter, eligibility, no fabrication); pricing; FAQ; an "Add to Claude" button.
- [ ] **Sign in:** passkey first, email code as the fallback.
- [ ] **Onboarding (4 steps):**
  1. Country and preferences form.
  2. Add the connector: copy the URL, plus a 3-step guide with screenshots.
  3. Install the plugin.
  4. "Paste your CV into Claude and say: set up my profile", then set up the daily scheduled task.
  - A progress checklist turns green as the server sees the first `get_profile` call and the first `submit_jobs` call.
- [ ] **Tracker:** a full-screen version of the tracker view, using the same components.
- [ ] **Insights (Pro only):** applications by status; interview rate by ghost band and by fit band (charts).
- [ ] **Billing:** current plan, usage (CVs this month), upgrade or cancel through the provider's hosted checkout.
- [ ] **Settings:**
  - profile versions
  - active sessions and tokens, with revoke
  - "Export all data" (JSON plus a zip of PDFs, ready within 1 minute)
  - "Delete account": hard-deletes within 24 hours through a worker. Sightings the user submitted are kept, but `submitted_by` is set to null.
- [ ] Privacy policy, in plain language and linked from the consent screen.
- [ ] **Performance budget:** LCP under 1.8 s on a mid-range phone over 4G, CLS under 0.05, Lighthouse accessibility score of 100. Use Playwright and Lighthouse CI.

**Billing:**
- [ ] Use a merchant of record (Paddle or Lemon Squeezy; Stripe doesn't onboard businesses registered in Pakistan). Ask the user which, and confirm it pays out to Pakistan.
- [ ] Hosted checkout only; we never touch card data.
- [ ] `POST /billing/webhook`: signature verified, idempotent on event ID, updates `users.plan`.
- [ ] Price point: ask the user.

**M6 gate:**
- [ ] All screens shipped within the budgets above.
- [ ] Checkout and webhook switch plans correctly, and free limits are enforced in the tools.
- [ ] Export and delete work end to end.
- [ ] 10–20 beta users onboarded.
- [ ] The weekly eval shows 80% or more band agreement (20 real jobs scored by Claude vs human judgment).
- [ ] Connector directory submission sent.

### 2.7 Scheduled jobs (Celery beat, UTC) — `app/workers/`
- [ ] **`recheck_open_jobs`, 01:00 daily:**
  - a plain GET on each open job's `apply_url`, at most 2 requests per second per domain
  - a 404 or 410, or a page that no longer contains the title, is a miss; 2 misses in a row close the job (`status='closed'`, `closed_at`)
  - add a `recheck` sighting when the job is found
  - SSRF guard:
    - http/https only
    - resolve DNS first and reject private, loopback and link-local IPs
    - no redirects to other hosts
    - 10-second timeout, 2 MB maximum body
    - an honest user agent with a contact URL
  - respect robots.txt
- [ ] **`recompute_ghost_signals`, 02:00 daily:** age and repost updates for all open jobs (`app/ghost/signals.recompute_signals`).
- [ ] **`reset_cv_quota`, 1st of the month at 00:05:** resets `cv_quota_used`.
- [ ] **`purge_deleted_users`, hourly:** hard-deletes accounts past their 24-hour window.
- [ ] **`weekly_weight_report`, Monday 03:00:** interview rate by ghost band from `applications`. If the Low band's rate isn't at least 2× the High band's, flag the weights for review. Never change the weights automatically.
- [ ] Profile key rotation: a job that re-encrypts `profiles.data` with the newest key version.

### 2.8 Ops, observability, CI, deploy
- [ ] Self-hosted Grafana dashboards. Alerts when the tool error rate exceeds 2% for 10 minutes, or CV compile p95 exceeds 15 s.
- [ ] CI pipeline: lint → type check → unit → integration → MCP contract → views → build images. Plus dependency scanning and secret scanning.
- [ ] Merging to `main` deploys to staging; a tagged release deploys to production. Migrations run as a release step before new containers start.
- [ ] Environments: local, staging (its own connector URL, used for the beta), production. Each needs managed Postgres, Redis and object storage.

---

## 3. Questions to ask the user when you reach them
- [ ] Hosting provider and domain, for staging and production. This also gives the plugin's MCP URL.
- [ ] Payment provider (Paddle or Lemon Squeezy) and the paid-tier price.
- [ ] SMTP provider and credentials.
- [ ] S3-compatible storage provider, and whether to use MinIO locally.
- [ ] Which actions count as "1 scan a day" for the free plan.
- [ ] Passkey credentials table (a DDL change).
- [ ] The first ATS seed list (200–500 companies).
- [ ] Whether to include contract/hourly platforms (Deel, Turing) at launch or later.
- [ ] Whether to keep user-uploaded LaTeX templates in v1, or only our three.
- [ ] Review of the eligibility golden table, the region map and the FX rates (§0).

---

## 4. Reference: tool contracts (already implemented; keep stable)

| Tool | Called by | Opens view | Scope |
|---|---|---|---|
| get_profile | model | — | profile |
| update_profile | model | profile-review | profile |
| submit_jobs | model | — | jobs |
| search_jobs | model | — | jobs |
| save_job_scores | model | shortlist | jobs |
| get_job | model | job-detail | jobs |
| generate_cv | model | cv-studio | cv |
| track_application | model | — | tracker |
| list_applications | model | tracker | tracker |
| update_company_health | model | — | jobs |
| ui_set_application_status | view only | — | tracker |
| ui_dismiss_job | view only | — | jobs |
| ui_resolve_profile_change | view only | — | profile |
| ui_get_cv_pdf_url | view only | — | cv |

**Rules:**
- `submit_jobs` is idempotent (a resubmit adds a sighting).
- The server computes `ghost_score = clamp(base + jd_quality_points, 0, 100)`; Claude never sends the final number. Bands: 0–29 low, 30–59 medium, 60+ high.
- Errors are MCP tool errors with a code (`quota_exceeded`, `validation_failed`, `not_found`, `rate_limited`, `forbidden`, `no_profile`, `too_long`, `unavailable`) and a sentence Claude can relay.
- Rate limits per user: `submit_jobs` 20/min, `generate_cv` 10/hour, everything else 60/min.
- Every tool call writes `audit_log` (tool name, user, counts — never personal content).
- `profiles.data` is AES-256-GCM encrypted (AAD = user id), decrypted only inside request scope, and never logged.
- Access tokens last 1 hour; refresh tokens last 30 days, rotate on every use, and reusing one revokes its whole family.
- Scopes: `jobs`, `profile`, `cv`, `tracker`.
