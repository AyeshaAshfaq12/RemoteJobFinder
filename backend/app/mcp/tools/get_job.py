"""get_job: full job, sightings timeline, ghost signals, and the user's score."""

from mcp.types import CallToolResult
from sqlalchemy import select

from app.db.models import (
    Application,
    Company,
    GhostSignals,
    Job,
    JobPostingHistory,
    JobScore,
    JobSighting,
)
from app.mcp.runtime import ToolCtx, ToolFail, result, run_tool
from app.mcp.tools._shared import health_source, job_summary, parse_id, user_country
from app.profiles.service import get_active

NAME = "get_job"
SCOPE = "jobs"
VIEW = "ui://rjf/job-detail.html"
DESCRIPTION = (
    "Get one job in full: the complete description, every sighting with its source page, "
    "repost history, ghost-risk reasons, and the user's fit score. Call it when the user opens "
    "or asks about a specific job, or before writing a CV for it."
)


async def get_job(job_id: str) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        jid = parse_id(job_id)
        row = (
            await ctx.session.execute(
                select(Job, Company, GhostSignals)
                .join(Company, Company.id == Job.company_id)
                .outerjoin(GhostSignals, GhostSignals.job_id == Job.id)
                .where(Job.id == jid)
            )
        ).first()
        if row is None:
            raise ToolFail("not_found", f"No job with id '{job_id}'.")
        job, company, sig = row
        active = await get_active(ctx.session, ctx.user_id)
        country = await user_country(ctx.session, ctx.user_id, active)

        # Sightings are shared data; submitted_by (personal) is never exposed.
        sightings = [
            {
                "seen_at": s.seen_at.isoformat(),
                "source_kind": s.source_kind,
                "source_url": s.source_url,
            }
            for s in await ctx.session.scalars(
                select(JobSighting).where(JobSighting.job_id == jid).order_by(JobSighting.seen_at)
            )
        ]
        history = await ctx.session.execute(
            select(JobPostingHistory, Job)
            .join(Job, Job.id == JobPostingHistory.job_id)
            .where(
                JobPostingHistory.company_id == job.company_id,
                JobPostingHistory.title_norm == job.title_norm,
            )
            .order_by(Job.first_seen_at)
        )
        postings = [
            {
                "job_id": str(j.id),
                "posted_at": (h.posted_at or j.first_seen_at.date()).isoformat(),
                "first_seen_at": j.first_seen_at.isoformat(),
                "status": j.status,
                "is_this_job": j.id == jid,
            }
            for h, j in history.all()
        ]
        score = await ctx.session.scalar(
            select(JobScore)
            .where(JobScore.user_id == ctx.user_id, JobScore.job_id == jid)
            .order_by(JobScore.profile_version.desc())
            .limit(1)
        )
        app_row = await ctx.session.scalar(
            select(Application).where(
                Application.user_id == ctx.user_id, Application.job_id == jid
            )
        )
        reasons = [dict(r) for r in (sig.reasons if sig else [])]
        for r in reasons:
            if r.get("code") == "company_shrinking" and not r.get("source_url"):
                r["source_url"] = health_source(company)

        out = job_summary(job, company, sig, country, include_jd=True)
        out["ghost_reasons"] = reasons
        out.update(
            company_health={
                "flag": company.health_flag,
                "note": company.health_note,
                "checked_at": company.health_checked_at.isoformat()
                if company.health_checked_at
                else None,
            },
            sightings=sightings,
            postings=postings,
            repost_count_90d=sig.repost_count_90d if sig else 0,
            score=(
                {
                    "profile_version": score.profile_version,
                    "fit_band": score.fit_band,
                    "fit_summary": score.fit_summary,
                    "must_haves_met": score.must_haves_met,
                    "gaps": score.gaps,
                    "ghost_score": score.ghost_score,
                    "ghost_band": score.ghost_band,
                    "dismissed": score.dismissed,
                }
                if score
                else None
            ),
            application={"id": str(app_row.id), "status": app_row.status} if app_row else None,
        )
        band = f"{score.fit_band}, ghost {score.ghost_band}" if score else "not scored yet"
        return result(
            f"{job.title} at {company.name} ({out['eligibility_label']}; {band}). "
            f"Seen {len(sightings)} time(s); {len(postings)} posting(s) of this title. "
            f"Apply: {job.apply_url}",
            out,
        )

    return await run_tool(NAME, SCOPE, body)
