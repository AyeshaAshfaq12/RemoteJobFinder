"""save_job_scores: save fit + JD-quality scores in bulk; shows the ranked shortlist."""

from datetime import date
from typing import Any

from mcp.types import CallToolResult
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.cv.schema import MasterProfile
from app.db.models import Company, GhostSignals, Job, JobScore
from app.ghost.score import final_score, jd_quality_points
from app.mcp.runtime import ToolCtx, ToolFail, result, run_tool
from app.mcp.tools._shared import job_summary, parse_id, require_profile, user_country
from app.mcp.tools.schemas import JobScoreIn

NAME = "save_job_scores"
SCOPE = "jobs"
VIEW = "ui://rjf/shortlist.html"
DESCRIPTION = (
    "Save your fit band, evidence, gaps, and JD-quality flags for up to 50 jobs at once; the "
    "server adds its own ghost-risk facts and computes the final ghost score. Call it once per "
    "scan after scoring; it opens the user's ranked shortlist."
)

BAND_ORDER = {"match": 0, "stretch": 1, "reach": 2, "skip": 3}


def _check_evidence(score: JobScoreIn, bullet_ids: set[str]) -> list[str]:
    problems = []
    for m in score.must_haves_met:
        bid = m.get("evidence_bullet_id")
        if not m.get("requirement"):
            problems.append(f"{score.job_id}: a must_haves_met item has no 'requirement'")
        if bid not in bullet_ids:
            problems.append(f"{score.job_id}: evidence_bullet_id '{bid}' is not in the profile")
    for g in score.gaps:
        if not g.get("requirement"):
            problems.append(f"{score.job_id}: a gap has no 'requirement'")
        if g.get("severity") not in ("low", "high"):
            problems.append(f"{score.job_id}: gap severity must be 'low' or 'high'")
    return problems


async def save_job_scores(
    scores: list[JobScoreIn] = Field(min_length=1, max_length=50),
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        active = await require_profile(ctx.session, ctx.user_id)
        bullet_ids = set(MasterProfile.model_validate(active.profile).all_bullets())
        country = await user_country(ctx.session, ctx.user_id, active)

        ids = [parse_id(s.job_id) for s in scores]
        rows = (
            await ctx.session.execute(
                select(Job, Company, GhostSignals)
                .join(Company, Company.id == Job.company_id)
                .outerjoin(GhostSignals, GhostSignals.job_id == Job.id)
                .where(Job.id.in_(ids))
            )
        ).all()
        found = {job.id: (job, company, sig) for job, company, sig in rows}
        missing = [s.job_id for s, i in zip(scores, ids, strict=True) if i not in found]
        problems = [f"{m}: no such job" for m in missing]
        for s in scores:
            problems += _check_evidence(s, bullet_ids)
        if problems:
            raise ToolFail(
                "validation_failed",
                f"{len(problems)} problem(s); fix them and call save_job_scores again.",
                problems,
            )

        shortlist: list[dict[str, Any]] = []
        hidden: list[dict[str, Any]] = []
        skipped = 0
        for s, job_id in zip(scores, ids, strict=True):
            job, company, sig = found[job_id]
            base = sig.base_score if sig else 0
            ghost, band = final_score(base, s.jd_quality_flags)
            values = {
                "user_id": ctx.user_id,
                "job_id": job_id,
                "profile_version": active.version,
                "fit_band": s.fit_band,
                "fit_summary": s.fit_summary,
                "must_haves_met": s.must_haves_met,
                "gaps": s.gaps,
                "jd_quality_points": jd_quality_points(s.jd_quality_flags),
                "ghost_score": ghost,
                "ghost_band": band,
            }
            stmt = insert(JobScore).values(**values)
            await ctx.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[JobScore.user_id, JobScore.job_id, JobScore.profile_version],
                    set_={k: v for k, v in values.items()
                          if k not in ("user_id", "job_id", "profile_version")},
                )
            )
            if s.fit_band == "skip":
                skipped += 1
                continue
            item = job_summary(job, company, sig, country)
            jd_reasons = [
                {"code": f, "points": p, "detail": f.replace("_", " "), "source_url": None}
                for f in s.jd_quality_flags
                if (p := jd_quality_points([f]))
            ]
            item.update(
                fit_band=s.fit_band,
                fit_summary=s.fit_summary,
                must_haves_met=s.must_haves_met,
                gaps=s.gaps,
                ghost_score=ghost,
                ghost_band=band,
                ghost_reasons=[*(sig.reasons if sig else []), *jd_reasons],
            )
            (hidden if band == "high" else shortlist).append(item)

        # Band, then ghost score ascending, then newest first (two stable sorts).
        shortlist.sort(key=lambda j: j["last_seen_at"], reverse=True)
        shortlist.sort(key=lambda j: (BAND_ORDER[j["fit_band"]], j["ghost_score"]))

        counts = {
            "scored": len(scores),
            "shown": len(shortlist),
            "match": sum(1 for j in shortlist if j["fit_band"] == "match"),
            "stretch": sum(1 for j in shortlist if j["fit_band"] == "stretch"),
            "reach": sum(1 for j in shortlist if j["fit_band"] == "reach"),
            "hidden_ghost": len(hidden),
            "skipped": skipped,
        }
        ctx.audit.update(counts)
        best = shortlist[0] if shortlist else None
        text = (
            f"Saved {len(scores)} score(s). Shortlist: {counts['shown']} job(s) "
            f"({counts['match']} Match, {counts['stretch']} Stretch, {counts['reach']} Reach); "
            f"{counts['hidden_ghost']} hidden as likely ghost jobs; {skipped} skipped."
        )
        if best:
            text += (
                f" Top: {best['title']} at {best['company']} ({best['fit_band']}, ghost "
                f"{best['ghost_band']}): {best['fit_summary']}"
            )
        return result(
            text,
            {
                "date": date.today().isoformat(),
                "profile_version": active.version,
                "counts": counts,
                "jobs": shortlist,
                "hidden": hidden,
            },
        )

    return await run_tool(NAME, SCOPE, body)
