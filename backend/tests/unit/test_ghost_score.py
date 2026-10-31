"""20 hand-built fixtures for the ghost base score (Build Spec section 7, M1 gate)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.ghost.score import Signals, band, base_score, final_score, jd_quality_points
from app.ghost.signals import age_in_days, count_gap_reposts


def sig(
    ats: bool = True,
    reposts: int = 0,
    age: int | None = 5,
    salary: bool = False,
    health: str = "unknown",
    submitters: int = 1,
) -> Signals:
    return Signals(ats, reposts, age, salary, health, submitters)


# (id, signals, expected base score, expected reason codes) — each total worked out by hand.
FIXTURES: list[tuple[str, Signals, int, list[str]]] = [
    ("clean_on_ats", sig(), 0, []),
    ("not_on_ats", sig(ats=False), 35, ["not_on_company_ats"]),
    ("repost_once", sig(reposts=1), 10, ["repost_1_90d"]),
    ("repost_twice", sig(reposts=2), 25, ["repost_2plus_90d"]),
    ("repost_five", sig(reposts=5), 25, ["repost_2plus_90d"]),
    ("age_30_not_counted", sig(age=30), 0, []),
    ("age_31", sig(age=31), 8, ["age_over_30d"]),
    ("age_45_still_30_band", sig(age=45), 8, ["age_over_30d"]),
    ("age_46", sig(age=46), 15, ["age_over_45d"]),
    ("age_unknown", sig(age=None), 0, []),
    ("shrinking", sig(health="shrinking"), 15, ["company_shrinking"]),
    ("growing_no_points", sig(health="growing"), 0, []),
    ("salary_listed_floors_at_0", sig(salary=True), 0, ["salary_listed"]),
    ("seen_by_3", sig(submitters=3), 0, ["seen_by_many"]),
    ("seen_by_2_not_many", sig(submitters=2), 0, []),
    (
        "off_ats_with_salary",
        sig(ats=False, salary=True),
        25,
        ["not_on_company_ats", "salary_listed"],
    ),
    (
        "classic_ghost",
        sig(ats=False, reposts=3, age=60, health="shrinking"),
        90,  # 35 + 25 + 15 + 15
        ["not_on_company_ats", "repost_2plus_90d", "age_over_45d", "company_shrinking"],
    ),
    (
        "everything_bad_capped",
        sig(ats=False, reposts=4, age=90, health="shrinking", submitters=0),
        90,
        ["not_on_company_ats", "repost_2plus_90d", "age_over_45d", "company_shrinking"],
    ),
    (
        "medium_mix",
        sig(ats=False, reposts=1, age=10, salary=True, submitters=4),
        30,  # 35 + 10 - 10 - 5
        ["not_on_company_ats", "repost_1_90d", "salary_listed", "seen_by_many"],
    ),
    (
        "old_repost_on_ats",
        sig(reposts=2, age=40, salary=True),
        23,  # 25 + 8 - 10
        ["repost_2plus_90d", "age_over_30d", "salary_listed"],
    ),
]


def test_twenty_fixtures() -> None:
    assert len(FIXTURES) == 20


@pytest.mark.parametrize(
    ("name", "signals", "score", "codes"), FIXTURES, ids=[f[0] for f in FIXTURES]
)
def test_base_score(name: str, signals: Signals, score: int, codes: list[str]) -> None:
    got, reasons = base_score(signals)
    assert got == score
    assert [r.code for r in reasons] == codes
    assert all(r.detail for r in reasons)


def test_reason_details_carry_numbers() -> None:
    _, reasons = base_score(sig(reposts=3, age=50))
    details = {r.code: r.detail for r in reasons}
    assert details["repost_2plus_90d"] == "Reposted 3 times in 90 days"
    assert details["age_over_45d"] == "Posted 50 days ago"
    assert reasons[0].to_json()["points"] == 25


@pytest.mark.parametrize(
    ("base", "flags", "expected"),
    [
        (0, [], (0, "low")),
        (25, ["no_team"], (28, "low")),
        (28, ["no_team"], (31, "medium")),
        (29, [], (29, "low")),
        (30, [], (30, "medium")),
        (55, ["talent_pool_wording"], (61, "high")),
        (2, ["named_hiring_contact"], (0, "low")),
        (
            98,
            ["no_responsibilities", "no_team", "talent_pool_wording", "generic_template"],
            (100, "high"),
        ),
    ],
)
def test_final_score(base: int, flags: list[str], expected: tuple[int, str]) -> None:
    assert final_score(base, flags) == expected


def test_jd_quality_points_and_bands() -> None:
    assert jd_quality_points(["no_responsibilities", "named_hiring_contact"]) == -1
    assert [band(s) for s in (0, 29, 30, 59, 60, 100)] == [
        "low",
        "low",
        "medium",
        "medium",
        "high",
        "high",
    ]


def test_count_gap_reposts() -> None:
    now = datetime(2026, 10, 29, tzinfo=UTC)

    def d(days: int) -> datetime:
        return now - timedelta(days=days)

    assert count_gap_reposts([], now) == 0
    assert count_gap_reposts([d(10), d(5), d(1)], now) == 0
    assert count_gap_reposts([d(60), d(30)], now) == 1  # 30-day gap
    assert count_gap_reposts([d(80), d(50), d(20)], now) == 2
    assert count_gap_reposts([d(200), d(150)], now) == 0  # outside 90 days


def test_age_in_days() -> None:
    seen = datetime(2026, 10, 1, tzinfo=UTC)
    assert age_in_days(date(2026, 9, 1), seen, date(2026, 10, 29)) == 58
    assert age_in_days(None, seen, date(2026, 10, 29)) == 28
    assert age_in_days(date(2026, 11, 5), seen, date(2026, 10, 29)) == 0
