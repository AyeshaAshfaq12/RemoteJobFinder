"""get_profile: profile, preferences, and the crawl query plan."""

from mcp.types import CallToolResult

from app.discovery.crawl_plan import crawl_plan, known_careers_urls
from app.mcp.runtime import ToolCtx, result, run_tool
from app.mcp.tools.schemas import CrawlPlan, GetProfileOut, Preferences
from app.profiles.service import get_active

NAME = "get_profile"
SCOPE = "profile"
VIEW = None
DESCRIPTION = (
    "Get the user's approved Master Profile, job preferences, and today's crawl plan (search "
    "queries, seed career pages, fetch budget). Call this first in every job scan and before "
    "writing a CV."
)


async def _body(ctx: ToolCtx) -> CallToolResult:
    active = await get_active(ctx.session, ctx.user_id)
    if active is None:
        out = GetProfileOut(
            profile_version=None,
            profile=None,
            preferences=None,
            crawl_plan=CrawlPlan(queries=[], seed_career_urls=[], fetch_budget=0),
        )
        return result(
            "No approved profile yet. Ask the user to paste their CV, build a MasterProfile from "
            "it, and call update_profile. Do not crawl until a profile is approved.",
            out,
        )
    prefs = Preferences.model_validate(active.preferences)
    plan = crawl_plan(prefs, await known_careers_urls(ctx.session, ctx.user_id))
    out = GetProfileOut(
        profile_version=active.version, profile=active.profile, preferences=prefs, crawl_plan=plan
    )
    ctx.audit["queries"] = len(plan.queries)
    return result(
        f"Profile v{active.version} for {active.profile.get('name', 'the user')}. "
        f"Targets: {', '.join(prefs.target_titles)}; country {prefs.country_code}. "
        f"Crawl plan: {len(plan.queries)} queries, {len(plan.seed_career_urls)} seed pages, "
        f"fetch budget {plan.fetch_budget}.",
        out,
    )


async def get_profile() -> CallToolResult:
    return await run_tool(NAME, SCOPE, _body)
