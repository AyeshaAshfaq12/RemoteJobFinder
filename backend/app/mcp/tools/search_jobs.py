"""search_jobs: eligible jobs already in the store, unscored first."""

from datetime import timedelta

from mcp.types import CallToolResult
from pydantic import Field
from sqlalchemy import and_, any_, exists, false, func, literal, or_, select

from app.db.models import Company, GhostSignals, Job, JobScore
from app.mcp.runtime import ToolCtx, result, run_tool
from app.mcp.tools._shared import job_summary, now_utc, require_profile, user_country
from app.mcp.tools.schemas import Preferences, SearchJobsIn
from app.discovery.normalize import normalize_company

NAME = "search_jobs"
SCOPE = "jobs"
VIEW = None
DESCRIPTION = (
    "List open jobs from our store that the user can take (worldwide, regions that include "
    "their country, or unclear ones for you to judge), unscored ones first, with full job "
    "descriptions. Call it after submit_jobs to get the jobs you need to score."
)


async def search_jobs(
    only_unscored: bool = True,
    since_days: int = Field(14, ge=1, le=90),
    title_query: str | None = None,
    limit: int = Field(25, ge=1, le=50),
) -> CallToolResult:
    args = SearchJobsIn(
        only_unscored=only_unscored, since_days=since_days, title_query=title_query, limit=limit
    )

    async def body(ctx: ToolCtx) -> CallToolResult:
        active = await require_profile(ctx.session, ctx.user_id)
        prefs = Preferences.model_validate(active.preferences)
        country = await user_country(ctx.session, ctx.user_id, active)

        scored = exists().where(
            JobScore.user_id == ctx.user_id,
            JobScore.job_id == Job.id,
            JobScore.profile_version == active.version,
        )
        dismissed = exists().where(
            JobScore.user_id == ctx.user_id, JobScore.job_id == Job.id, JobScore.dismissed
        )
        eligible = or_(
            Job.eligibility.in_(("worldwide", "unclear")),
            and_(
                Job.eligibility.in_(("region_open", "restricted")),
                literal(country) == any_(Job.allowed_countries) if country else false(),
            ),
        )
        q = (
            select(Job, Company, GhostSignals, scored.label("is_scored"))
            .join(Company, Company.id == Job.company_id)
            .outerjoin(GhostSignals, GhostSignals.job_id == Job.id)
            .where(
                Job.status == "open",
                Job.last_seen_at >= now_utc() - timedelta(days=args.since_days),
                eligible,
                ~dismissed,
            )
        )
        excluded = [normalize_company(c) for c in prefs.excluded_companies if c.strip()]
        if excluded:
            q = q.where(Company.name_norm.not_in(excluded))
        if args.only_unscored:
            q = q.where(~scored)
        if args.title_query:
            t = args.title_query.lower()
            q = q.where(or_(Job.title_norm.ilike(f"%{t}%"), func.similarity(Job.title_norm, t) > 0.3))
        q = q.order_by(scored.asc(), Job.last_seen_at.desc()).limit(args.limit)

        rows = (await ctx.session.execute(q)).all()
        jobs = []
        for job, company, sig, is_scored in rows:
            item = job_summary(job, company, sig, country, include_jd=True)
            item["scored"] = bool(is_scored)
            jobs.append(item)
        ctx.audit["returned"] = len(jobs)
        unscored = sum(1 for j in jobs if not j["scored"])
        return result(
            f"{len(jobs)} job(s) returned, {unscored} not yet scored for profile "
            f"v{active.version}. Score each with fit-rubric and ghost-rubric, then call "
            "save_job_scores once with all scores.",
            {"profile_version": active.version, "jobs": jobs},
        )

    return await run_tool(NAME, SCOPE, body)
