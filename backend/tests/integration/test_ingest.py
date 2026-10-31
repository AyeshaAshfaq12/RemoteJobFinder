import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, GhostSignals, Job, JobPostingHistory, JobSighting, User
from app.discovery.ingest import ingest_job
from app.mcp.tools.schemas import SubmittedJob

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)

JD = (
    "Acme builds payments infrastructure for emerging markets. As a Backend Engineer on the "
    "Payments team you will design and run Python services on Postgres, own APIs end to end, "
    "and work with the product manager and designers. Requirements: 4+ years of backend "
    "experience, strong SQL, and experience running services in production. We hire worldwide."
)


def make_job(**overrides: Any) -> SubmittedJob:
    data: dict[str, Any] = {
        "title": "Senior Backend Engineer",
        "company_name": "Acme Inc.",
        "company_domain": "acme.io",
        "location_text": "Remote - Worldwide",
        "remote_type": "remote",
        "employment_type": "full_time",
        "salary_text": "$5k-7k/month",
        "posted_at": date(2026, 10, 20),
        "apply_url": "https://jobs.lever.co/acme/123",
        "source_url": "https://jobs.lever.co/acme/123",
        "source_kind": "ats",
        "jd_text": JD,
    }
    data.update(overrides)
    return SubmittedJob.model_validate(data)


async def make_user(session: AsyncSession, email: str) -> uuid.UUID:
    user = User(email=email, country_code="PK")
    session.add(user)
    await session.flush()
    return user.id


async def count(session: AsyncSession, model: type[Any]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_migration_creates_spec_tables(session: AsyncSession) -> None:
    rows = await session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    )
    tables = {r[0] for r in rows}
    assert {
        "users",
        "profiles",
        "companies",
        "jobs",
        "job_sightings",
        "job_postings_history",
        "ghost_signals",
        "job_scores",
        "cvs",
        "applications",
        "audit_log",
        "oauth_clients",
        "oauth_authorization_codes",
        "oauth_tokens",
    } <= tables
    idx = {r[0] for r in await session.execute(text("SELECT indexname FROM pg_indexes"))}
    assert {
        "jobs_dedupe",
        "jobs_open_recent",
        "jobs_title_trgm",
        "companies_name_trgm",
        "one_active_profile",
        "sightings_job_time",
        "applications_followup",
    } <= idx


async def test_same_job_twice_yields_one_job_two_sightings(session: AsyncSession) -> None:
    user = await make_user(session, "a@example.com")
    first = await ingest_job(session, make_job(), user, NOW)
    second = await ingest_job(session, make_job(), user, NOW + timedelta(hours=1))
    await session.commit()

    assert first.is_new
    assert not second.is_new
    assert first.job_id == second.job_id
    assert (first.sightings, second.sightings) == (1, 2)
    assert await count(session, Job) == 1
    assert await count(session, JobSighting) == 2


async def test_new_job_fields_and_signals(session: AsyncSession) -> None:
    r = await ingest_job(session, make_job(), None, NOW)
    job = await session.get(Job, r.job_id)
    assert job is not None
    assert job.title_norm == "senior backend engineer"
    assert job.seniority == "senior"
    assert job.eligibility == "worldwide"
    assert r.eligibility.eligible_for("PK")
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (
        5000,
        7000,
        "USD",
        "month",
    )
    assert job.on_company_ats
    company = await session.get(Company, job.company_id)
    assert company is not None
    assert (company.domain, company.ats_type, company.ats_slug) == ("acme.io", "lever", "acme")
    assert company.careers_url == "https://jobs.lever.co/acme"
    assert r.needs_company_check

    sig = await session.get(GhostSignals, r.job_id)
    assert sig is not None
    assert (sig.on_company_ats, sig.salary_listed, sig.age_days) == (True, True, 9)
    assert sig.base_score == 0  # on ATS, salary listed (-10), clamped to 0
    assert [x["code"] for x in sig.reasons] == ["salary_listed"]


async def test_near_duplicate_adds_sighting(session: AsyncSession) -> None:
    a = await ingest_job(session, make_job(), None, NOW)
    edited = JD.replace("We hire worldwide.", "We hire worldwide!! Apply today.")
    b = await ingest_job(
        session,
        make_job(
            jd_text=edited, source_kind="remote_board", source_url="https://remoteok.com/jobs/9"
        ),
        None,
        NOW,
    )
    assert a.job_id == b.job_id
    assert not b.is_new
    assert await count(session, Job) == 1


async def test_repost_with_new_jd_counts_in_history(session: AsyncSession) -> None:
    await ingest_job(session, make_job(), None, NOW - timedelta(days=40))
    other_jd = (
        "Acme is hiring again. Senior Backend Engineer to scale our ledger, reconciliation, and "
        "settlement systems across 12 countries. You'll lead migrations to event sourcing, "
        "mentor engineers, and partner with finance. Kafka, Go, and Postgres experience matter "
        "most here, plus on-call ownership."
    )
    r = await ingest_job(
        session, make_job(jd_text=other_jd, posted_at=date(2026, 10, 25)), None, NOW
    )
    assert r.is_new
    assert await count(session, JobPostingHistory) == 2
    sig = await session.get(GhostSignals, r.job_id)
    assert sig is not None
    assert sig.repost_count_90d == 1
    assert "repost_1_90d" in [x["code"] for x in sig.reasons]


async def test_same_hash_after_gap_counts_as_repost(session: AsyncSession) -> None:
    await ingest_job(session, make_job(), None, NOW - timedelta(days=50))
    r = await ingest_job(session, make_job(), None, NOW)
    sig = await session.get(GhostSignals, r.job_id)
    assert sig is not None
    assert sig.repost_count_90d == 1


async def test_company_match_by_trigram_name(session: AsyncSession) -> None:
    a = await ingest_job(
        session,
        make_job(
            company_domain=None,
            company_name="Globex Corporation",
            apply_url="https://globex.example/jobs/1",
            source_url="https://globex.example/jobs/1",
            source_kind="careers_page",
        ),
        None,
        NOW,
    )
    b = await ingest_job(
        session,
        make_job(
            company_domain=None,
            company_name="Globex Corp.",
            title="Data Engineer",
            apply_url="https://remoteok.com/x",
            source_url="https://remoteok.com/x",
            source_kind="remote_board",
        ),
        None,
        NOW,
    )
    assert a.company_id == b.company_id
    assert await count(session, Company) == 1


async def test_not_on_ats_and_distinct_submitters(session: AsyncSession) -> None:
    users = [await make_user(session, f"u{i}@example.com") for i in range(3)]
    off = make_job(
        company_domain="initech.io",
        company_name="Initech",
        apply_url="https://remoteok.com/jobs/1",
        source_url="https://remoteok.com/jobs/1",
        source_kind="remote_board",
        salary_text=None,
    )
    r = None
    for u in users:
        r = await ingest_job(session, off, u, NOW)
    assert r is not None
    sig = await session.get(GhostSignals, r.job_id)
    assert sig is not None
    codes = [x["code"] for x in sig.reasons]
    assert codes == ["not_on_company_ats", "seen_by_many"]
    assert sig.base_score == 30


async def test_restricted_and_region_open_store_countries(session: AsyncSession) -> None:
    us = await ingest_job(
        session, make_job(location_text="Remote - US only", title="SRE"), None, NOW
    )
    apac = await ingest_job(
        session, make_job(location_text="Remote - APAC", title="QA Engineer"), None, NOW
    )
    us_job = await session.get(Job, us.job_id)
    apac_job = await session.get(Job, apac.job_id)
    assert us_job is not None
    assert apac_job is not None
    assert (us_job.eligibility, us_job.allowed_countries) == ("restricted", ["US"])
    assert apac_job.eligibility == "region_open"
    assert apac_job.allowed_countries is not None
    assert "PK" in apac_job.allowed_countries
    assert not us.eligibility.eligible_for("PK")
    assert apac.eligibility.eligible_for("PK")
