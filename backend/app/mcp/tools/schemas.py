"""Public MCP tool schemas (Build Spec section 5). Changing these needs human sign-off."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

EligibilityLit = Literal["worldwide", "region_open", "restricted", "unclear"]
ApplicationStatus = Literal[
    "saved", "applying", "applied", "interviewing", "offer", "rejected", "withdrawn", "ghosted"
]
JdFlag = Literal[
    "no_responsibilities",
    "no_team",
    "talent_pool_wording",
    "generic_template",
    "named_hiring_contact",
]


class Preferences(BaseModel):
    target_titles: list[str] = Field(min_length=1, max_length=8)
    seniority_floor: Literal["junior", "mid", "senior"] = "mid"
    allow_stretch: bool = True
    employment_types: list[Literal["full_time", "contract"]] = ["full_time"]
    salary_floor_usd_month: int | None = None
    us_overlap_hours: float = Field(0, ge=0, le=8)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    excluded_companies: list[str] = []


class CrawlPlan(BaseModel):
    queries: list[str]  # e.g. 'site:jobs.lever.co "backend engineer" remote'
    seed_career_urls: list[HttpUrl]  # known companies to re-visit
    fetch_budget: int = 30  # max page fetches per scan


class GetProfileOut(BaseModel):
    profile_version: int | None
    profile: dict[str, Any] | None  # MasterProfile, section 8
    preferences: Preferences | None
    crawl_plan: CrawlPlan


class SubmittedJob(BaseModel):
    title: str = Field(max_length=200)
    company_name: str = Field(max_length=200)
    company_domain: str | None = None
    location_text: str = Field(max_length=500)
    remote_type: Literal["remote", "hybrid", "onsite"]
    employment_type: Literal["full_time", "contract", "part_time", "internship"] | None = None
    salary_text: str | None = None  # raw; server parses it
    posted_at: date | None = None
    apply_url: HttpUrl
    source_url: HttpUrl
    source_kind: Literal["ats", "careers_page", "remote_board", "search_result"]
    jd_text: str = Field(min_length=200, max_length=40_000)


class SubmitJobsIn(BaseModel):
    jobs: list[SubmittedJob] = Field(min_length=1, max_length=50)


class SubmitJobResult(BaseModel):
    job_id: str
    is_new: bool
    sightings: int
    eligibility: EligibilityLit
    eligible_for_user: bool
    ghost_base_score: int
    needs_scoring: bool
    # Soft signal (decided 2026-10-29): required overlap exceeds the user's us_overlap_hours.
    tz_conflict: bool = False


class SearchJobsIn(BaseModel):
    only_unscored: bool = True
    since_days: int = Field(14, ge=1, le=90)
    title_query: str | None = None
    limit: int = Field(25, ge=1, le=50)


class JobScoreIn(BaseModel):
    job_id: str
    fit_band: Literal["match", "stretch", "reach", "skip"]
    fit_summary: str = Field(max_length=280)
    must_haves_met: list[dict[str, Any]]  # {requirement, evidence_bullet_id}
    gaps: list[dict[str, Any]]  # {requirement, transferable_from?, severity: 'low'|'high'}
    jd_quality_flags: list[JdFlag]


class SaveJobScoresIn(BaseModel):
    scores: list[JobScoreIn] = Field(min_length=1, max_length=50)


class GenerateCvIn(BaseModel):
    job_id: str
    template: Literal["classic", "modern", "compact"] = "classic"
    content: dict[str, Any]  # CvContent, section 8
    kit: dict[str, Any]  # {cover_note, screening_answers[], recruiter_dm, gap_report[]}


class TrackApplicationIn(BaseModel):
    job_id: str
    status: ApplicationStatus
    notes: str | None = None
    cv_id: str | None = None
