"""submit_jobs pipeline (Build Spec section 6).

normalize -> company match -> dedupe -> eligibility -> sighting -> signal recompute,
in one transaction per job (the caller owns the transaction).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Job, JobPostingHistory, JobSighting
from app.discovery.dedupe import NEAR_JD_JACCARD, NEAR_TITLE_SIMILARITY, is_near_duplicate
from app.discovery.eligibility import EligibilityResult, classify, tz_min_overlap_hours
from app.discovery.normalize import (
    ats_from_url,
    detect_seniority,
    is_on_company_ats,
    jd_hash,
    normalize_company,
    normalize_domain,
    normalize_title,
)
from app.discovery.salary import parse_salary
from app.ghost.signals import recompute_signals
from app.mcp.tools.schemas import SubmittedJob

COMPANY_NAME_SIMILARITY = 0.85
HEALTH_CHECK_MAX_AGE = timedelta(days=7)


@dataclass(frozen=True)
class IngestResult:
    job_id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    is_new: bool
    sightings: int
    eligibility: EligibilityResult
    tz_min_overlap_hours: float | None
    ghost_base_score: int
    needs_company_check: bool


async def match_company(session: AsyncSession, job: SubmittedJob) -> Company:
    """Exact domain, then ATS slug, then trigram name similarity > 0.85, else create."""
    domain = normalize_domain(job.company_domain)
    name_norm = normalize_company(job.company_name)
    ats = ats_from_url(str(job.apply_url)) or ats_from_url(str(job.source_url))

    company: Company | None = None
    if domain:
        company = await session.scalar(select(Company).where(Company.domain == domain))
    if company is None and ats:
        company = await session.scalar(
            select(Company).where(Company.ats_type == ats.ats_type, Company.ats_slug == ats.slug)
        )
    if company is None and name_norm:
        sim = func.similarity(Company.name_norm, name_norm)
        row = await session.execute(
            select(Company, sim).where(sim > COMPANY_NAME_SIMILARITY).order_by(sim.desc()).limit(1)
        )
        found = row.first()
        if found is not None:
            company = found[0]

    if company is None:
        careers_url = None
        if ats:
            careers_url = f"https://{_ats_host(ats.ats_type)}/{ats.slug}"
        elif job.source_kind == "careers_page":
            careers_url = str(job.source_url)
        stmt = (
            insert(Company)
            .values(
                name=job.company_name.strip(),
                name_norm=name_norm or job.company_name.strip().lower(),
                domain=domain,
                ats_type=ats.ats_type if ats else None,
                ats_slug=ats.slug if ats else None,
                careers_url=careers_url,
            )
            .on_conflict_do_nothing(index_elements=[Company.domain])
            .returning(Company.id)
        )
        new_id = await session.scalar(stmt)
        if new_id is None:  # lost a race on the unique domain
            company = await session.scalar(select(Company).where(Company.domain == domain))
        else:
            company = await session.get(Company, new_id)
        assert company is not None
        return company

    # Fill in what we learned without overwriting known facts.
    changes: dict[str, object] = {}
    if domain and not company.domain:
        changes["domain"] = domain
    if ats and not company.ats_type:
        changes["ats_type"] = ats.ats_type
        changes["ats_slug"] = ats.slug
        if not company.careers_url:
            changes["careers_url"] = f"https://{_ats_host(ats.ats_type)}/{ats.slug}"
    if changes:
        await session.execute(update(Company).where(Company.id == company.id).values(**changes))
        await session.refresh(company)
    return company


def _ats_host(ats_type: str) -> str:
    return {
        "greenhouse": "job-boards.greenhouse.io",
        "lever": "jobs.lever.co",
        "ashby": "jobs.ashbyhq.com",
        "workable": "apply.workable.com",
    }[ats_type]


async def _find_existing(
    session: AsyncSession, company_id: uuid.UUID, title_norm: str, hash_: str, jd_text: str
) -> Job | None:
    exact = await session.scalar(
        select(Job).where(
            Job.company_id == company_id, Job.title_norm == title_norm, Job.jd_hash == hash_
        )
    )
    if exact is not None:
        return exact
    sim = func.similarity(Job.title_norm, title_norm)
    candidates = await session.scalars(
        select(Job).where(
            Job.company_id == company_id, Job.status == "open", sim > NEAR_TITLE_SIMILARITY
        )
    )
    for cand in candidates:
        if is_near_duplicate(jd_text, cand.jd_text, threshold=NEAR_JD_JACCARD):
            return cand
    return None


async def ingest_job(
    session: AsyncSession,
    job: SubmittedJob,
    submitted_by: uuid.UUID | None,
    now: datetime | None = None,
) -> IngestResult:
    now = now or datetime.now(UTC)
    company = await match_company(session, job)

    title_norm = normalize_title(job.title) or job.title.strip().lower()
    hash_ = jd_hash(job.jd_text)
    elig = classify(job.location_text, job.jd_text)
    tz_hours = tz_min_overlap_hours(job.location_text, job.jd_text)
    on_ats = is_on_company_ats([str(job.apply_url), str(job.source_url)], company.domain)

    existing = await _find_existing(session, company.id, title_norm, hash_, job.jd_text)
    is_new = existing is None
    if existing is not None:
        job_id = existing.id
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                last_seen_at=now,
                on_company_ats=Job.on_company_ats | on_ats,
                status="open",
                closed_at=None,
            )
        )
    else:
        salary = parse_salary(job.salary_text)
        stmt = (
            insert(Job)
            .values(
                company_id=company.id,
                title=job.title.strip(),
                title_norm=title_norm,
                seniority=detect_seniority(job.title, job.jd_text),
                location_text=job.location_text.strip(),
                eligibility=elig.eligibility,
                allowed_countries=sorted(elig.allowed_countries)
                if elig.allowed_countries
                else None,
                tz_min_overlap_hours=tz_hours,
                remote_type=job.remote_type,
                employment_type=job.employment_type,
                salary_min=salary.min if salary else None,
                salary_max=salary.max if salary else None,
                salary_currency=salary.currency if salary else None,
                salary_period=salary.period if salary else None,
                posted_at=job.posted_at,
                apply_url=str(job.apply_url),
                on_company_ats=on_ats,
                jd_text=job.jd_text,
                jd_hash=hash_,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_nothing(index_elements=[Job.company_id, Job.title_norm, Job.jd_hash])
            .returning(Job.id)
        )
        new_id = await session.scalar(stmt)
        if new_id is None:  # a concurrent submit inserted it first: treat as exact match
            is_new = False
            raced = await _find_existing(session, company.id, title_norm, hash_, job.jd_text)
            assert raced is not None
            job_id = raced.id
            await session.execute(update(Job).where(Job.id == job_id).values(last_seen_at=now))
        else:
            job_id = new_id
            # Every posting goes into history; repost count = rows in 90 days - 1.
            await session.execute(
                insert(JobPostingHistory)
                .values(
                    company_id=company.id,
                    title_norm=title_norm,
                    job_id=job_id,
                    posted_at=job.posted_at or now.date(),
                )
                .on_conflict_do_nothing()
            )

    session.add(
        JobSighting(
            job_id=job_id,
            source_kind=job.source_kind,
            source_url=str(job.source_url),
            seen_at=now,
            submitted_by=submitted_by,
        )
    )
    await session.flush()
    sightings = await session.scalar(
        select(func.count()).select_from(JobSighting).where(JobSighting.job_id == job_id)
    )
    base = await recompute_signals(session, job_id, now)

    stored = await session.get(Job, job_id, populate_existing=True)
    assert stored is not None
    await session.refresh(stored)
    stored_elig = EligibilityResult(
        stored.eligibility,  # type: ignore[arg-type]
        frozenset(stored.allowed_countries) if stored.allowed_countries else None,
        elig.rule,
        elig.matched,
    )
    needs_check = (
        company.health_checked_at is None or now - company.health_checked_at > HEALTH_CHECK_MAX_AGE
    )
    return IngestResult(
        job_id=job_id,
        company_id=company.id,
        company_name=company.name,
        is_new=is_new,
        sightings=int(sightings or 0),
        eligibility=stored_elig,
        tz_min_overlap_hours=float(stored.tz_min_overlap_hours)
        if stored.tz_min_overlap_hours is not None
        else None,
        ghost_base_score=base,
        needs_company_check=needs_check,
    )
