"""Compute and store ghost_signals for a job from shared job data (Build Spec section 7)."""

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, GhostSignals, Job, JobPostingHistory, JobSighting
from app.ghost.score import Signals, base_score

REPOST_WINDOW_DAYS = 90
REPOST_GAP_DAYS = 21
SEEN_BY_MANY_DAYS = 7


def count_gap_reposts(seen_at: list[datetime], now: datetime) -> int:
    """Same-hash reappearances after a gap > 21 days, within the last 90 days.

    Counted as reposts (decided 2026-10-29).
    """
    window_start = now - timedelta(days=REPOST_WINDOW_DAYS)
    ordered = sorted(seen_at)
    return sum(
        1
        for prev, cur in itertools.pairwise(ordered)
        if cur >= window_start and (cur - prev) > timedelta(days=REPOST_GAP_DAYS)
    )


def age_in_days(posted_at: date | None, first_seen_at: datetime, today: date) -> int:
    start = posted_at or first_seen_at.date()
    return max(0, (today - start).days)


async def gather_signals(session: AsyncSession, job: Job, now: datetime) -> Signals:
    window_start = (now - timedelta(days=REPOST_WINDOW_DAYS)).date()

    # Every job of this (company, title_norm) is in history; the earliest one is the original.
    history_rows = await session.execute(
        select(func.count())
        .select_from(JobPostingHistory)
        .join(Job, Job.id == JobPostingHistory.job_id)
        .where(
            JobPostingHistory.company_id == job.company_id,
            JobPostingHistory.title_norm == job.title_norm,
            func.coalesce(JobPostingHistory.posted_at, func.date(Job.first_seen_at))
            >= window_start,
        )
    )
    history_reposts = max(0, int(history_rows.scalar_one()) - 1)

    seen = await session.execute(select(JobSighting.seen_at).where(JobSighting.job_id == job.id))
    gap_reposts = count_gap_reposts([r[0] for r in seen], now)

    submitters = await session.execute(
        select(func.count(func.distinct(JobSighting.submitted_by))).where(
            JobSighting.job_id == job.id,
            JobSighting.submitted_by.is_not(None),
            JobSighting.seen_at >= now - timedelta(days=SEEN_BY_MANY_DAYS),
        )
    )

    company = await session.get(Company, job.company_id, populate_existing=True)
    health = (company.health_flag if company else None) or "unknown"

    return Signals(
        on_company_ats=job.on_company_ats,
        repost_count_90d=history_reposts + gap_reposts,
        age_days=age_in_days(job.posted_at, job.first_seen_at, now.date()),
        salary_listed=job.salary_min is not None,
        company_health=health,
        distinct_submitters_7d=int(submitters.scalar_one()),
        health_source_url=None,
    )


async def recompute_signals(
    session: AsyncSession, job_id: uuid.UUID, now: datetime | None = None
) -> int:
    """Recompute and upsert ghost_signals for one job. Returns the base score."""
    now = now or datetime.now(UTC)
    job = await session.get(Job, job_id, populate_existing=True)
    if job is None:
        raise LookupError(f"job {job_id} not found")
    sig = await gather_signals(session, job, now)
    score, reasons = base_score(sig)
    values = {
        "job_id": job.id,
        "on_company_ats": sig.on_company_ats,
        "repost_count_90d": sig.repost_count_90d,
        "age_days": sig.age_days,
        "salary_listed": sig.salary_listed,
        "company_health": sig.company_health,
        "base_score": score,
        "reasons": [r.to_json() for r in reasons],
        "computed_at": now,
    }
    stmt = insert(GhostSignals).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[GhostSignals.job_id],
        set_={k: v for k, v in values.items() if k != "job_id"},
    )
    await session.execute(stmt)
    return score
