from pathlib import Path

import pytest

from app.discovery.eligibility import classify, tz_conflict, tz_min_overlap_hours

GOLDEN = Path(__file__).parent / "data" / "eligibility_golden.tsv"


def _load() -> list[tuple[str, str, set[str], set[str], str]]:
    rows = []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t") + [""] * 5
        loc, expected, inc, exc, jd = cols[:5]
        rows.append((loc, expected, set(inc.split()), set(exc.split()), jd))
    return rows


CASES = _load()


def _correct(loc: str, expected: str, inc: set[str], exc: set[str], jd: str) -> bool:
    r = classify(loc, jd)
    if r.eligibility != expected:
        return False
    allowed = r.allowed_countries or frozenset()
    return inc <= allowed and not (exc & allowed)


def test_golden_table_has_150_cases() -> None:
    assert len(CASES) == 150


def test_golden_accuracy_at_least_95_percent() -> None:
    wrong = [c[0] + (" | " + c[4] if c[4] else "") for c in CASES if not _correct(*c)]
    accuracy = 1 - len(wrong) / len(CASES)
    assert accuracy >= 0.95, f"{accuracy:.1%} correct; wrong: {wrong}"


@pytest.mark.parametrize(("loc", "expected", "inc", "exc", "jd"), CASES, ids=[c[0] for c in CASES])
def test_golden_case(loc: str, expected: str, inc: set[str], exc: set[str], jd: str) -> None:
    r = classify(loc, jd)
    assert r.eligibility == expected
    allowed = r.allowed_countries or frozenset()
    assert inc <= allowed, f"missing {inc - allowed}"
    assert not (exc & allowed), f"unexpected {exc & allowed}"


@pytest.mark.parametrize(
    ("loc", "country", "eligible"),
    [
        ("Remote - Worldwide", "PK", True),
        ("Remote - APAC", "PK", True),
        ("Remote - EMEA", "PK", False),
        ("Remote - US only", "US", True),
        ("Remote - US only", "PK", False),
        ("Remote - EU only", "DE", True),
        ("Remote (US)", "US", False),
        ("Remote - APAC", None, False),
    ],
)
def test_eligible_for(loc: str, country: str | None, eligible: bool) -> None:
    assert classify(loc).eligible_for(country) is eligible


@pytest.mark.parametrize(
    ("jd", "hours"),
    [
        ("We need 4 hours overlap with US Eastern time.", 4.0),
        ("Requires 3+ hours of daily overlap with PST.", 3.0),
        ("An overlap of at least 2 hours with CET.", 2.0),
        ("You must work EST hours.", 8.0),
        ("Work PST business hours", 8.0),
        ("Flexible hours, async first.", None),
        ("12 hours overlap", 8.0),
    ],
)
def test_tz_overlap(jd: str, hours: float | None) -> None:
    assert tz_min_overlap_hours("Remote", jd) == hours


def test_tz_conflict_is_soft_comparison() -> None:
    assert tz_conflict(4.0, 2.0)
    assert not tz_conflict(4.0, 4.0)
    assert not tz_conflict(None, 0.0)
