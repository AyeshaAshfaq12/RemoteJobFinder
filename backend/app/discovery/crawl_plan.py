"""Crawl plan built by get_profile (Build Spec section 6)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Job, JobScore
from app.discovery.normalize import ATS_SITES, BOARDS
from app.mcp.tools.schemas import CrawlPlan, Preferences

MAX_QUERIES = 24
MAX_SEEDS = 10
FETCH_BUDGET = 30


def crawl_plan(prefs: Preferences, known_careers_urls: list[str]) -> CrawlPlan:
    q = [f'site:{s} "{t}" remote' for t in prefs.target_titles for s in ATS_SITES]
    q += [f"site:{b} {t}" for t in prefs.target_titles for b in BOARDS]
    q += [f'"{t}" remote "worldwide" OR "anywhere" job' for t in prefs.target_titles]
    return CrawlPlan(
        queries=q[:MAX_QUERIES],
        seed_career_urls=known_careers_urls[:MAX_SEEDS],  # type: ignore[arg-type]
        fetch_budget=FETCH_BUDGET,
    )


async def known_careers_urls(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Careers pages of companies behind the user's Match/Stretch jobs, most recent first."""
    rows = await session.execute(
        select(Company.careers_url, JobScore.scored_at)
        .join(Job, Job.company_id == Company.id)
        .join(JobScore, JobScore.job_id == Job.id)
        .where(
            JobScore.user_id == user_id,
            JobScore.fit_band.in_(("match", "stretch")),
            Company.careers_url.is_not(None),
        )
        .order_by(JobScore.scored_at.desc())
        .limit(100)
    )
    seen: list[str] = []
    for url, _ in rows:
        if url and url not in seen:
            seen.append(url)
    return seen[:MAX_SEEDS]
