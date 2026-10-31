"""update_company_health: record Claude's news check (layoffs, freezes, funding)."""

from typing import Literal

from mcp.types import CallToolResult
from pydantic import Field, HttpUrl
from sqlalchemy import select

from app.db.models import Company, Job
from app.ghost.signals import recompute_signals
from app.mcp.runtime import ToolCtx, ToolFail, result, run_tool
from app.mcp.tools._shared import now_utc, parse_id

NAME = "update_company_health"
SCOPE = "jobs"
VIEW = None
DESCRIPTION = (
    "Record what recent news says about a company's hiring health (growing, stable, "
    "shrinking, or unknown) with a one-line note and the source URL. Call it for each company "
    "listed in submit_jobs' needs_company_check after searching the last 6 months of news."
)


async def update_company_health(
    company_id: str,
    flag: Literal["growing", "stable", "shrinking", "unknown"],
    note: str = Field(max_length=300),
    source_url: HttpUrl | None = None,
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        cid = parse_id(company_id, "company")
        company = await ctx.session.get(Company, cid)
        if company is None:
            raise ToolFail("not_found", f"No company with id '{company_id}'.")
        if flag != "unknown" and source_url is None:
            raise ToolFail(
                "validation_failed", "A source_url is required unless flag is 'unknown'."
            )
        changed = company.health_flag != flag
        company.health_flag = flag
        company.health_note = f"{note.strip()} Source: {source_url}" if source_url else note.strip()
        company.health_checked_at = now_utc()
        await ctx.session.flush()
        recomputed = 0
        if changed:
            open_jobs = await ctx.session.scalars(
                select(Job.id).where(Job.company_id == cid, Job.status == "open")
            )
            for job_id in list(open_jobs):
                await recompute_signals(ctx.session, job_id)
                recomputed += 1
        ctx.audit.update(flag=flag, recomputed=recomputed)
        return result(
            f"{company.name}: marked {flag}. Ghost signals recomputed for {recomputed} open job(s).",
            {"company_id": str(cid), "flag": flag, "recomputed_jobs": recomputed},
        )

    return await run_tool(NAME, SCOPE, body)
