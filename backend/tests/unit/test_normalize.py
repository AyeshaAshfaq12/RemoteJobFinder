import pytest

from app.discovery.normalize import (
    ats_from_url,
    detect_seniority,
    host_of,
    is_on_company_ats,
    jaccard,
    jd_hash,
    normalize_company,
    normalize_domain,
    normalize_title,
    shingles,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Senior Backend Engineer", "senior backend engineer"),
        ("Sr. Backend Engineer", "senior backend engineer"),
        ("Sr Backend Eng", "senior backend engineer"),
        ("SWE II", "software engineer ii"),
        ("ML Engineer", "machine learning engineer"),
        ("Jr. Frontend Developer", "junior frontend developer"),
        ("Backend Engineer (Remote)", "backend engineer"),
        ("Backend Engineer [Contract]", "backend engineer"),
        ("Backend Engineer - Remote", "backend engineer"),
        ("Backend Engineer - EMEA", "backend engineer"),
        ("Backend Engineer | Berlin", "backend engineer"),
        ("Backend Engineer – Germany", "backend engineer"),
        ("Backend Engineer - Payments Team", "backend engineer"),
        ("Engineering Manager - Backend", "engineering manager backend"),
        ("Front-end   Developer", "front-end developer"),
        ("C++ Developer", "c++ developer"),
        ("Senior .NET Engineer, Platform", "senior .net engineer platform"),
    ],
)
def test_normalize_title(raw: str, expected: str) -> None:
    assert normalize_title(raw) == expected


@pytest.mark.parametrize(
    ("title", "jd", "expected"),
    [
        ("Software Engineer Intern", "", "intern"),
        ("Junior Developer", "", "junior"),
        ("Jr Developer", "", "junior"),
        ("Senior Engineer", "", "senior"),
        ("Staff Engineer", "", "staff"),
        ("Tech Lead", "", "lead"),
        ("Principal Engineer", "", "lead"),
        ("Backend Engineer", "Requires 1 year of experience", "unknown"),
        ("Backend Engineer", "Requires 1 years of experience", "junior"),
        ("Backend Engineer", "3+ years of Python", "mid"),
        ("Backend Engineer", "You have 6 years experience", "senior"),
        ("Backend Engineer", "10+ years building systems", "staff"),
        ("Backend Engineer", "No experience number here", "unknown"),
    ],
)
def test_detect_seniority(title: str, jd: str, expected: str) -> None:
    assert detect_seniority(title, jd) == expected


def test_jd_hash_ignores_urls_emails_dates_case_whitespace() -> None:
    a = "We build things.  Apply at https://x.com/jobs/1 or jobs@x.com by 2026-10-01.\n\nGreat team"
    b = "WE BUILD THINGS. Apply at https://y.io/a or hr@y.io by March 3, 2027. Great   team"
    assert jd_hash(a) == jd_hash(b)
    assert len(jd_hash(a)) == 64
    assert jd_hash(a) != jd_hash("Something else entirely")


def test_jd_hash_uses_first_4000_chars() -> None:
    base = "x " * 2500
    assert jd_hash(base + "tail one") == jd_hash(base + "tail two")


def test_shingles_and_jaccard() -> None:
    a = shingles("one two three four")
    assert a == {("one", "two", "three"), ("two", "three", "four")}
    assert shingles("one two") == {("one", "two")}
    assert shingles("") == set()
    assert jaccard(a, a) == 1.0
    assert jaccard(set(), set()) == 1.0
    assert jaccard(a, shingles("five six seven")) == 0.0


def test_urls_and_domains() -> None:
    assert host_of("https://www.Example.com/jobs") == "example.com"
    assert normalize_domain("https://www.acme.io/careers") == "acme.io"
    assert normalize_domain("ACME.io/") == "acme.io"
    assert normalize_domain("") is None
    assert normalize_domain(None) is None


def test_on_company_ats() -> None:
    assert is_on_company_ats(["https://jobs.lever.co/acme/123"], None)
    assert is_on_company_ats(["https://careers.acme.io/jobs/1"], "acme.io")
    assert not is_on_company_ats(["https://remoteok.com/jobs/1"], "acme.io")
    assert not is_on_company_ats(["https://notacme.io/x"], "acme.io")


@pytest.mark.parametrize(
    ("url", "ats", "slug"),
    [
        ("https://jobs.lever.co/Acme/abc-123", "lever", "acme"),
        ("https://boards.greenhouse.io/acme/jobs/1", "greenhouse", "acme"),
        ("https://job-boards.greenhouse.io/acme/jobs/1", "greenhouse", "acme"),
        ("https://jobs.ashbyhq.com/acme/uuid", "ashby", "acme"),
        ("https://apply.workable.com/acme/j/ABC/", "workable", "acme"),
    ],
)
def test_ats_from_url(url: str, ats: str, slug: str) -> None:
    ref = ats_from_url(url)
    assert ref is not None
    assert (ref.ats_type, ref.slug) == (ats, slug)


def test_ats_from_url_non_ats() -> None:
    assert ats_from_url("https://acme.io/careers") is None
    assert ats_from_url("https://boards.greenhouse.io/embed/job_app") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acme, Inc.", "acme"),
        ("Acme Ltd", "acme"),
        ("Acme GmbH", "acme"),
        ("Procter & Gamble Co.", "procter and gamble"),
        ("Systems Ltd (Pvt) Limited", "systems"),
    ],
)
def test_normalize_company(raw: str, expected: str) -> None:
    assert normalize_company(raw) == expected
