"""Ghost-risk scoring (Build Spec section 7): server base score + Claude's JD-quality points."""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.ghost.weights import JD_FLAG_POINTS, WEIGHTS

GhostBand = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Reason:
    code: str
    points: int
    detail: str
    source_url: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Signals:
    on_company_ats: bool
    repost_count_90d: int
    age_days: int | None
    salary_listed: bool
    company_health: str
    distinct_submitters_7d: int
    ats_source_url: str | None = None
    health_source_url: str | None = None


def clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def base_score(sig: Signals) -> tuple[int, list[Reason]]:
    r: list[Reason] = []
    if not sig.on_company_ats:
        r.append(
            Reason(
                "not_on_company_ats",
                WEIGHTS["not_on_company_ats"],
                "Not found on the company's own careers page or ATS",
            )
        )
    if sig.repost_count_90d >= 2:
        r.append(
            Reason(
                "repost_2plus_90d",
                WEIGHTS["repost_2plus_90d"],
                f"Reposted {sig.repost_count_90d} times in 90 days",
            )
        )
    elif sig.repost_count_90d == 1:
        r.append(Reason("repost_1_90d", WEIGHTS["repost_1_90d"], "Reposted once in 90 days"))
    if sig.age_days is not None and sig.age_days > 45:
        r.append(Reason("age_over_45d", WEIGHTS["age_over_45d"], f"Posted {sig.age_days} days ago"))
    elif sig.age_days is not None and sig.age_days > 30:
        r.append(Reason("age_over_30d", WEIGHTS["age_over_30d"], f"Posted {sig.age_days} days ago"))
    if sig.company_health == "shrinking":
        r.append(
            Reason(
                "company_shrinking",
                WEIGHTS["company_shrinking"],
                "Recent layoffs or hiring freeze reported",
                sig.health_source_url,
            )
        )
    if sig.salary_listed:
        r.append(Reason("salary_listed", WEIGHTS["salary_listed"], "Salary range is listed"))
    if sig.distinct_submitters_7d >= 3:
        r.append(
            Reason("seen_by_many", WEIGHTS["seen_by_many"], "Found by several users this week")
        )
    return clamp(sum(x.points for x in r)), r


def jd_quality_points(flags: Iterable[str]) -> int:
    return sum(JD_FLAG_POINTS[f] for f in flags)


def band(score: int) -> GhostBand:
    return "low" if score < 30 else "medium" if score < 60 else "high"


def final_score(base: int, flags: Iterable[str]) -> tuple[int, GhostBand]:
    s = clamp(base + jd_quality_points(flags))
    return s, band(s)
