"""submit_jobs: send crawled jobs; returns dedupe results and ghost base scores."""

from typing import Any

from mcp.types import CallToolResult
from pydantic import Field
from sqlalchemy import select

from app.db.models import JobScore
from app.discovery.eligibility import tz_conflict
from app.discovery.ingest import ingest_job
from app.mcp.runtime import ToolCtx, result, run_tool
from app.mcp.tools._shared import user_country
from app.mcp.tools.schemas import Preferences, SubmitJobResult, SubmittedJob
from app.profiles.service import get_active

NAME = "submit_jobs"
SCOPE = "jobs"
VIEW = None
DESCRIPTION = (
    "Submit up to 50 job postings you extracted while crawling, with fields copied exactly as "
    "written. Submitting a known job again only records a new sighting. Call it in batches "
    "during a scan, then follow up on needs_company_check."
)


async def submit_jobs(
    jobs: list[SubmittedJob] = Field(min_length=1, max_length=50),
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        active = await get_active(ctx.session, ctx.user_id)
        country = await user_country(ctx.session, ctx.user_id, active)
        overlap = Preferences.model_validate(active.preferences).us_overlap_hours if active else 0
        results: list[SubmitJobResult] = []
        check: dict[str, dict[str, Any]] = {}
        for job in jobs:
            async with ctx.session.begin_nested():  # one transaction (savepoint) per job
                r = await ingest_job(ctx.session, job, ctx.user_id)
            needs_scoring = True
            if active is not None:
                scored = await ctx.session.scalar(
                    select(JobScore.job_id).where(
                        JobScore.user_id == ctx.user_id,
                        JobScore.job_id == r.job_id,
                        JobScore.profile_version == active.version,
                    )
                )
                needs_scoring = scored is None
            results.append(
                SubmitJobResult(
                    job_id=str(r.job_id),
                    is_new=r.is_new,
                    sightings=r.sightings,
                    eligibility=r.eligibility.eligibility,
                    eligible_for_user=r.eligibility.eligible_for(country),
                    ghost_base_score=r.ghost_base_score,
                    needs_scoring=needs_scoring,
                    tz_conflict=tz_conflict(r.tz_min_overlap_hours, overlap),
                )
            )
            if r.needs_company_check:
                check[str(r.company_id)] = {"company_id": str(r.company_id), "name": r.company_name}

        new = sum(1 for r in results if r.is_new)
        eligible = sum(1 for r in results if r.eligible_for_user)
        unclear = sum(1 for r in results if r.eligibility == "unclear")
        ctx.audit.update(submitted=len(results), new=new, eligible=eligible)
        lines = [
            f"Saved {len(results)} job(s): {new} new, {len(results) - new} already known. "
            f"{eligible} eligible for the user's country ({country or 'unknown'})."
        ]
        if unclear:
            lines.append(
                f"{unclear} have unclear location rules: read those JDs and decide whether the "
                "user's country is allowed."
            )
        if check:
            names = ", ".join(c["name"] for c in check.values())
            lines.append(
                f"Check company health (layoffs, freezes, funding in the last 6 months) and call "
                f"update_company_health for: {names}."
            )
        return result(
            " ".join(lines),
            {"results": [r.model_dump() for r in results],
             "needs_company_check": list(check.values())},
        )

    return await run_tool(NAME, SCOPE, body)
