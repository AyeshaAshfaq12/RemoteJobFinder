"""Helpers shared by tool modules: ids, user context, job serialization."""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, GhostSignals, Job, User
from app.discovery.eligibility import EligibilityResult
from app.discovery.salary import to_usd_month
from app.mcp.runtime import ToolFail
from app.mcp.tools.schemas import Preferences
from app.profiles.service import StoredProfile, get_active

_URL = re.compile(r"https?://\S+")


def parse_id(value: str, what: str = "job") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ToolFail("not_found", f"No {what} with id '{value}'.") from exc


async def require_profile(session: AsyncSession, user_id: uuid.UUID) -> StoredProfile:
    active = await get_active(session, user_id)
    if active is None:
        raise ToolFail(
            "no_profile",
            "There is no approved profile yet. Ask the user for their CV, call update_profile, "
            "and have them approve it.",
        )
    return active


async def user_country(
    session: AsyncSession, user_id: uuid.UUID, active: StoredProfile | None
) -> str | None:
    if active is not None:
        return str(Preferences.model_validate(active.preferences).country_code)
    user = await session.get(User, user_id)
    return user.country_code if user else None


def eligibility_of(job: Job) -> EligibilityResult:
    return EligibilityResult(
        job.eligibility,  # type: ignore[arg-type]
        frozenset(job.allowed_countries) if job.allowed_countries else None,
        None,
        None,
    )


def salary_view(job: Job) -> dict[str, Any] | None:
    if job.salary_min is None:
        return None
    lo = to_usd_month(job.salary_min, job.salary_currency, job.salary_period)
    hi = to_usd_month(job.salary_max or job.salary_min, job.salary_currency, job.salary_period)
    return {
        "min": job.salary_min,
        "max": job.salary_max,
        "currency": job.salary_currency,
        "period": job.salary_period,
        "usd_month_min": round(lo) if lo is not None else None,
        "usd_month_max": round(hi) if hi is not None else None,
    }


def eligibility_label(job: Job, country: str | None) -> str:
    """Short pill text, e.g. 'Worldwide', 'Region incl. PK', 'US only'."""
    if job.eligibility == "worldwide":
        return "Worldwide"
    if job.eligibility == "unclear":
        return "Location unclear"
    countries = job.allowed_countries or []
    if job.eligibility == "restricted":
        return f"{'/'.join(countries) if len(countries) <= 3 else 'Restricted'} only"
    if country and country in countries:
        return f"Region incl. {country}"
    return "Region (not incl. you)" if country else "Region"


def health_source(company: Company | None) -> str | None:
    if company is None or not company.health_note:
        return None
    urls = _URL.findall(company.health_note)
    return urls[-1].rstrip(").,") if urls else None


def job_summary(
    job: Job,
    company: Company | None,
    sig: GhostSignals | None,
    country: str | None,
    *,
    include_jd: bool = False,
) -> dict[str, Any]:
    elig = eligibility_of(job)
    out: dict[str, Any] = {
        "job_id": str(job.id),
        "title": job.title,
        "company": company.name if company else None,
        "company_id": str(job.company_id),
        "company_domain": company.domain if company else None,
        "location_text": job.location_text,
        "eligibility": job.eligibility,
        "eligibility_label": eligibility_label(job, country),
        "eligible_for_user": elig.eligible_for(country),
        "allowed_countries": job.allowed_countries,
        "tz_min_overlap_hours": float(job.tz_min_overlap_hours)
        if job.tz_min_overlap_hours is not None
        else None,
        "remote_type": job.remote_type,
        "employment_type": job.employment_type,
        "seniority": job.seniority,
        "salary": salary_view(job),
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "first_seen_at": job.first_seen_at.isoformat(),
        "last_seen_at": job.last_seen_at.isoformat(),
        "apply_url": job.apply_url,
        "on_company_ats": job.on_company_ats,
        "status": job.status,
        "ghost_base_score": sig.base_score if sig else None,
        "ghost_reasons": sig.reasons if sig else [],
    }
    if include_jd:
        out["jd_text"] = job.jd_text
    return out


def now_utc() -> datetime:
    return datetime.now(UTC)
