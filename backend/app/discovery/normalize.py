"""Normalization of submitted jobs (Build Spec section 6)."""

import hashlib
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from app.discovery.regions import is_location_phrase

ATS_SITES = (
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "apply.workable.com",
)
BOARDS = ("remotive.com", "remoteok.com", "himalayas.app", "weworkremotely.com")

Seniority = Literal["intern", "junior", "mid", "senior", "staff", "lead", "unknown"]
AtsType = Literal["greenhouse", "lever", "ashby", "workable", "other"]

# --- title_norm ---------------------------------------------------------------------------

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}")
# " - ", " | ", and en/em dashes with spaces. A bare hyphen ("front-end") is not a separator.
_SEPARATOR = re.compile(r"\s+[-–—|]\s+|\s*\|\s*")
_TEAM_WORDS = re.compile(r"\b(team|squad|tribe|org|organization|group|department|division)\b")
_SYNONYMS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsr\b\.?"), "senior"),
    (re.compile(r"\bjr\b\.?"), "junior"),
    (re.compile(r"\bswe\b"), "software engineer"),
    (re.compile(r"\beng\b"), "engineer"),
    (re.compile(r"\bml\b"), "machine learning"),
)
_DISALLOWED = re.compile(r"[^a-z0-9+#./& -]+")
_WS = re.compile(r"\s+")


def _names_location_or_team(segment: str) -> bool:
    return bool(_TEAM_WORDS.search(segment)) or is_location_phrase(segment)


def normalize_title(title: str) -> str:
    """Lowercase; drop bracketed text and location/team suffixes; map synonyms; tidy spaces."""
    t = _BRACKETS.sub(" ", title.lower())
    parts = _SEPARATOR.split(t)
    kept = [parts[0]]
    for part in parts[1:]:
        if _names_location_or_team(part):
            break
        kept.append(part)
    t = " ".join(kept)
    t = t.replace(",", " ")
    for pattern, repl in _SYNONYMS:
        t = pattern.sub(repl, t)
    t = _DISALLOWED.sub(" ", t)
    return _WS.sub(" ", t).strip(" ./&-")


# --- seniority ----------------------------------------------------------------------------

_TITLE_LEVEL = re.compile(r"\b(intern|internship|junior|jr|mid|senior|sr|staff|lead|principal)\b")
_LEVEL_MAP: dict[str, Seniority] = {
    "intern": "intern",
    "internship": "intern",
    "junior": "junior",
    "jr": "junior",
    "mid": "mid",
    "senior": "senior",
    "sr": "senior",
    "staff": "staff",
    "lead": "lead",
    "principal": "lead",
}
_YEARS = re.compile(r"(\d+)\+?\s*years")


def seniority_from_years(years: int) -> Seniority:
    if years <= 1:
        return "junior"
    if years <= 4:
        return "mid"
    if years <= 7:
        return "senior"
    return "staff"


def detect_seniority(title: str, jd_text: str) -> Seniority:
    m = _TITLE_LEVEL.search(title.lower())
    if m:
        return _LEVEL_MAP[m.group(1)]
    y = _YEARS.search(jd_text.lower())
    if y:
        return seniority_from_years(int(y.group(1)))
    return "unknown"


# --- jd_hash and shingles -----------------------------------------------------------------

_URL = re.compile(r"https?://\S+|www\.\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_DATE = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b"
    r"|\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b"
    rf"|\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\.?,?\s+\d{{4}}\b"
)


def normalize_jd(jd_text: str) -> str:
    t = jd_text.lower()
    t = _URL.sub(" ", t)
    t = _EMAIL.sub(" ", t)
    t = _DATE.sub(" ", t)
    return _WS.sub(" ", t).strip()


def jd_hash(jd_text: str) -> str:
    """sha256 of the normalized JD (lowercased; URLs, emails, dates removed), first 4,000 chars."""
    return hashlib.sha256(normalize_jd(jd_text)[:4000].encode("utf-8")).hexdigest()


_WORD = re.compile(r"[a-z0-9+#]+")


def shingles(jd_text: str, k: int = 3) -> set[tuple[str, ...]]:
    words = _WORD.findall(normalize_jd(jd_text))
    if len(words) < k:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


# --- URLs, companies, ATS -----------------------------------------------------------------


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def normalize_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    d = domain.strip().lower()
    if "//" in d:
        d = host_of(d)
    d = d.split("/")[0].removeprefix("www.").rstrip(".")
    return d or None


def _on_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def is_on_company_ats(urls: list[str], company_domain: str | None) -> bool:
    """True when any URL is on a public ATS host or on the company's own domain."""
    for url in urls:
        host = host_of(url)
        if any(_on_domain(host, site) for site in ATS_SITES):
            return True
        if company_domain and _on_domain(host, company_domain):
            return True
    return False


@dataclass(frozen=True)
class AtsRef:
    ats_type: AtsType
    slug: str


_ATS_PATTERNS: tuple[tuple[str, AtsType], ...] = (
    ("boards.greenhouse.io", "greenhouse"),
    ("job-boards.greenhouse.io", "greenhouse"),
    ("jobs.lever.co", "lever"),
    ("jobs.ashbyhq.com", "ashby"),
    ("apply.workable.com", "workable"),
)


def ats_from_url(url: str) -> AtsRef | None:
    """jobs.lever.co/<slug>/... -> AtsRef('lever', '<slug>')."""
    host = host_of(url)
    for ats_host, ats_type in _ATS_PATTERNS:
        if host == ats_host:
            first = urlsplit(url).path.strip("/").split("/")[0]
            if first and first not in {"embed", "j"}:
                return AtsRef(ats_type, first.lower())
    return None


_COMPANY_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|gmbh|ag|sa|sas|bv|plc|corp|corporation|co|pvt|"
    r"private|pte|oy|ab|as|srl|spa)\b\.?"
)


def normalize_company(name: str) -> str:
    t = name.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = _COMPANY_SUFFIX.sub(" ", t)
    return _WS.sub(" ", t).strip()
