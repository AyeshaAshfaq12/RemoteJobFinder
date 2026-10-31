"""Initial schema: Build Spec section 4 DDL plus OAuth tables.

Revision ID: 001
Revises:
Create Date: 2026-10-29
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# Section 4 of the Build Spec, verbatim. Do not edit without asking the human.
SPEC_DDL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         citext UNIQUE NOT NULL,
  name          text,
  country_code  char(2),
  plan          text NOT NULL DEFAULT 'free' CHECK (plan IN ('free','pro')),
  cv_quota_used int NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  deleted_at    timestamptz
);

CREATE TABLE profiles (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  version     int NOT NULL,
  data        bytea NOT NULL,
  preferences jsonb NOT NULL,
  -- 'superseded' added 2026-10-29 (approved by the human)
  status      text NOT NULL CHECK (status IN ('proposed','active','rejected','superseded')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, version)
);
CREATE UNIQUE INDEX one_active_profile ON profiles(user_id) WHERE status = 'active';

CREATE TABLE companies (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name              text NOT NULL,
  name_norm         text NOT NULL,
  domain            text UNIQUE,
  ats_type          text CHECK (ats_type IN ('greenhouse','lever','ashby','workable','other')),
  ats_slug          text,
  careers_url       text,
  health_note       text,
  health_flag       text CHECK (health_flag IN ('growing','stable','shrinking','unknown')) DEFAULT 'unknown',
  health_checked_at timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX companies_name_trgm ON companies USING gin (name_norm gin_trgm_ops);

CREATE TABLE jobs (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id           uuid NOT NULL REFERENCES companies(id),
  title                text NOT NULL,
  title_norm           text NOT NULL,
  seniority            text CHECK (seniority IN ('intern','junior','mid','senior','staff','lead','unknown')),
  location_text        text NOT NULL,
  eligibility          text NOT NULL CHECK (eligibility IN ('worldwide','region_open','restricted','unclear')),
  allowed_countries    char(2)[],
  tz_min_overlap_hours numeric(3,1),
  remote_type          text NOT NULL CHECK (remote_type IN ('remote','hybrid','onsite')),
  employment_type      text CHECK (employment_type IN ('full_time','contract','part_time','internship')),
  salary_min int, salary_max int, salary_currency char(3), salary_period text,
  posted_at            date,
  apply_url            text NOT NULL,
  on_company_ats       boolean NOT NULL DEFAULT false,
  jd_text              text NOT NULL,
  jd_hash              char(64) NOT NULL,
  status               text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  first_seen_at        timestamptz NOT NULL DEFAULT now(),
  last_seen_at         timestamptz NOT NULL DEFAULT now(),
  closed_at            timestamptz
);
CREATE UNIQUE INDEX jobs_dedupe ON jobs(company_id, title_norm, jd_hash);
CREATE INDEX jobs_open_recent ON jobs(status, last_seen_at DESC);
CREATE INDEX jobs_title_trgm ON jobs USING gin (title_norm gin_trgm_ops);

CREATE TABLE job_sightings (
  id           bigserial PRIMARY KEY,
  job_id       uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source_kind  text NOT NULL CHECK (source_kind IN ('ats','careers_page','remote_board','search_result','recheck')),
  source_url   text NOT NULL,
  seen_at      timestamptz NOT NULL DEFAULT now(),
  submitted_by uuid REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX sightings_job_time ON job_sightings(job_id, seen_at);

CREATE TABLE job_postings_history (
  company_id uuid NOT NULL REFERENCES companies(id),
  title_norm text NOT NULL,
  job_id     uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  posted_at  date,
  PRIMARY KEY (company_id, title_norm, job_id)
);

CREATE TABLE ghost_signals (
  job_id           uuid PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
  on_company_ats   boolean NOT NULL,
  repost_count_90d int NOT NULL,
  age_days         int,
  salary_listed    boolean NOT NULL,
  company_health   text NOT NULL,
  base_score       int NOT NULL,
  reasons          jsonb NOT NULL,
  computed_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE job_scores (
  user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id            uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  profile_version   int NOT NULL,
  fit_band          text NOT NULL CHECK (fit_band IN ('match','stretch','reach','skip')),
  fit_summary       text NOT NULL,
  must_haves_met    jsonb NOT NULL,
  gaps              jsonb NOT NULL,
  jd_quality_points int NOT NULL DEFAULT 0,
  ghost_score       int NOT NULL,
  ghost_band        text NOT NULL CHECK (ghost_band IN ('low','medium','high')),
  dismissed         boolean NOT NULL DEFAULT false,
  scored_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, job_id, profile_version)
);

CREATE TABLE cvs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id          uuid REFERENCES jobs(id) ON DELETE SET NULL,
  profile_version int NOT NULL,
  template        text NOT NULL,
  content         jsonb NOT NULL,
  tex_key         text NOT NULL,
  pdf_key         text,
  status          text NOT NULL CHECK (status IN ('queued','compiled','failed')),
  error           text,
  kit             jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE applications (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id       uuid NOT NULL REFERENCES jobs(id),
  cv_id        uuid REFERENCES cvs(id) ON DELETE SET NULL,
  status       text NOT NULL CHECK (status IN ('saved','applying','applied','interviewing','offer','rejected','withdrawn','ghosted')),
  applied_at   timestamptz,
  follow_up_at date,
  notes        text,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, job_id)
);
CREATE INDEX applications_followup ON applications(user_id, follow_up_at) WHERE status = 'applied';

CREATE TABLE audit_log (
  id      bigserial PRIMARY KEY,
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  action  text NOT NULL,
  meta    jsonb,
  at      timestamptz NOT NULL DEFAULT now()
);
"""

# OAuth 2.1 tables for the MCP SDK auth server (mcp.server.auth) with our Postgres provider.
# Codes and tokens are stored as SHA-256 hashes; refresh tokens carry a family_id so reuse of a
# rotated refresh token revokes the whole family. Every row is scoped by user_id.
OAUTH_DDL = """
CREATE TABLE oauth_clients (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id                varchar(64) NOT NULL UNIQUE,
  client_secret_hash       char(64),
  client_id_issued_at      int NOT NULL DEFAULT 0,
  client_secret_expires_at int,
  client_metadata          jsonb NOT NULL
);

CREATE TABLE oauth_authorization_codes (
  code_hash                        char(64) PRIMARY KEY,
  user_id                          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id                        varchar(64) NOT NULL,
  redirect_uri                     text NOT NULL,
  redirect_uri_provided_explicitly boolean NOT NULL,
  scope                            text NOT NULL DEFAULT '',
  code_challenge                   text NOT NULL,
  resource                         text,
  expires_at                       double precision NOT NULL
);

CREATE TABLE oauth_tokens (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id                varchar(64) NOT NULL,
  family_id                uuid NOT NULL,
  access_token_hash        char(64) NOT NULL UNIQUE,
  refresh_token_hash       char(64) UNIQUE,
  scope                    text NOT NULL DEFAULT '',
  resource                 text,
  issued_at                int NOT NULL,
  access_expires_at        int NOT NULL,
  refresh_expires_at       int,
  access_token_revoked_at  int,
  refresh_token_revoked_at int
);
CREATE INDEX oauth_tokens_family ON oauth_tokens(family_id);
CREATE INDEX oauth_tokens_user ON oauth_tokens(user_id);
"""

DROP = """
DROP TABLE IF EXISTS oauth_tokens, oauth_authorization_codes, oauth_clients,
  audit_log, applications, cvs, job_scores, ghost_signals, job_postings_history,
  job_sightings, jobs, companies, profiles, users CASCADE;
"""


def upgrade() -> None:
    op.execute(SPEC_DDL)
    op.execute(OAUTH_DDL)


def downgrade() -> None:
    op.execute(DROP)
