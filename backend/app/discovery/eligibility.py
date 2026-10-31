"""Location eligibility (Build Spec section 6). Rules run in order; the first match wins.

Rules 1-3 look at location_text and the JD; rules 4-5 look at location_text only, because JDs
name office cities and customer countries that say nothing about who can be hired.
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.discovery.regions import EU, find_countries, find_regions, has_city

Eligibility = Literal["worldwide", "region_open", "restricted", "unclear"]

_US = r"(?:us|u\.s\.?|usa|u\.s\.a\.?|united states(?: of america)?)"

# Rule 1: restricted to the US.
_RULE1 = re.compile(
    rf"\b{_US}[\s-]*only\b"
    rf"|\bmust\s+be\s+(?:located|based)\s+in\s+(?:the\s+)?{_US}(?![a-z])"
    rf"|\banywhere\s+in\s+(?:the\s+)?{_US}(?![a-z])"
    rf"|\b{_US}\s+citizens?(?:hip)?\b"
    r"|\bsecurity\s+clearance\b"
    r"|\bw-?2\b"
)

# Rule 2: restricted to the EU, UK, or Canada.
_RULE2: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r"\beu[\s-]*only\b|\bright\s+to\s+work\s+in\s+(?:the\s+)?eu\b"), EU),
    (
        re.compile(
            r"\b(?:uk|u\.k\.)[\s-]*only\b|\bright\s+to\s+work\s+in\s+(?:the\s+)?(?:uk|u\.k\.)"
            r"(?![a-z])"
        ),
        frozenset({"GB"}),
    ),
    (re.compile(r"\bcanada[\s-]*only\b"), frozenset({"CA"})),
)

# Rule 3: worldwide. In the JD only unambiguous phrases count; "global" there is noise.
_RULE3_LOCATION = re.compile(
    r"\b(worldwide|anywhere|global(?:ly)?|work\s+from\s+anywhere|fully\s+distributed)\b"
)
_RULE3_JD = re.compile(
    r"\b(work\s+from\s+anywhere|fully\s+distributed|remote[\s-]+worldwide"
    r"|anywhere\s+in\s+the\s+world|hire\s+(?:from\s+)?anywhere)\b"
)
# "Anywhere in Europe" / "worldwide except the US" are not worldwide; fall through.
_SCOPED_WORLDWIDE = re.compile(
    r"\b(?:anywhere|worldwide|global(?:ly)?)\s+(?:in|within|across|from|except|excluding)\b"
    r"(?!\s+the\s+world)"
)

_REMOTE = re.compile(r"\bremote\b")

# Timezone overlap: "4 hours overlap", "4+ hours of overlap", "overlap of at least 3 hours",
# "must work EST hours" (no number = full 8-hour overlap, decided 2026-10-29).
_TZ_NUMBER = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*hours?\s+(?:of\s+)?(?:\w+\s+){0,2}overlap"
    r"|overlap\s+(?:of\s+)?(?:at\s+least\s+|minimum\s+(?:of\s+)?)?(\d+(?:\.\d+)?)\s*\+?\s*hours?"
)
_TZ_ZONE = re.compile(
    r"\b(est|edt|et|pst|pdt|pt|cst|mst|cet|cest)\s+(?:working\s+|business\s+)?hours\b"
)
FULL_OVERLAP_HOURS = 8.0


@dataclass(frozen=True)
class EligibilityResult:
    eligibility: Eligibility
    allowed_countries: frozenset[str] | None
    rule: int | None
    matched: str | None

    def eligible_for(self, country_code: str | None) -> bool:
        """Worldwide, or region_open/restricted lists that include the user's country.

        Restricted jobs count for users in the restricted country (decided 2026-10-29).
        'unclear' is False here; Claude decides from the JD.
        """
        if self.eligibility == "worldwide":
            return True
        if self.eligibility == "unclear" or not country_code or not self.allowed_countries:
            return False
        return country_code.upper() in self.allowed_countries


def classify(location_text: str, jd_text: str = "") -> EligibilityResult:
    loc = location_text.lower()
    jd = jd_text.lower()

    for text in (loc, jd):
        m = _RULE1.search(text)
        if m:
            return EligibilityResult("restricted", frozenset({"US"}), 1, m.group(0))

    for text in (loc, jd):
        for pattern, restricted_to in _RULE2:
            m = pattern.search(text)
            if m:
                return EligibilityResult("restricted", restricted_to, 2, m.group(0))

    if not _SCOPED_WORLDWIDE.search(loc):
        m = _RULE3_LOCATION.search(loc)
        if m:
            return EligibilityResult("worldwide", None, 3, m.group(0))
    region_countries, region_names = find_regions(location_text)
    countries = find_countries(location_text)
    names_place = bool(region_names or countries or has_city(location_text))

    # A JD saying "fully distributed" doesn't override a location that names a place.
    if not names_place and not _SCOPED_WORLDWIDE.search(jd):
        m = _RULE3_JD.search(jd)
        if m:
            return EligibilityResult("worldwide", None, 3, m.group(0))

    if region_names or len(countries) >= 2:
        allowed = frozenset(region_countries | countries)
        matched = ", ".join(region_names + sorted(countries))
        return EligibilityResult("region_open", allowed, 4, matched)

    if _REMOTE.search(loc) and (countries or has_city(location_text)):
        return EligibilityResult("unclear", None, 5, None)

    return EligibilityResult("unclear", None, None, None)


def tz_min_overlap_hours(location_text: str, jd_text: str) -> float | None:
    text = f"{location_text}\n{jd_text}".lower()
    m = _TZ_NUMBER.search(text)
    if m:
        hours = float(m.group(1) or m.group(2))
        return min(hours, FULL_OVERLAP_HOURS)
    if _TZ_ZONE.search(text):
        return FULL_OVERLAP_HOURS
    return None


def tz_conflict(required_hours: float | None, user_overlap_hours: float) -> bool:
    """Soft signal only: never hides a job (decided 2026-10-29)."""
    return required_hours is not None and required_hours > user_overlap_hours
