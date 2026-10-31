import pytest

from app.discovery.salary import Salary, fx_table, parse_salary, to_usd_month


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$4k-6k/month", Salary(4000, 6000, "USD", "month")),
        ("USD 60,000 - 80,000 per year", Salary(60000, 80000, "USD", "year")),
        ("PKR 300,000 - 400,000 per month", Salary(300000, 400000, "PKR", "month")),
        ("€50k–€70k annually", Salary(50000, 70000, "EUR", "year")),
        ("£45,000 - £55,000 p.a.", Salary(45000, 55000, "GBP", "year")),
        ("$40-60 per hour", Salary(40, 60, "USD", "hour")),
        ("$50/hr", Salary(50, 50, "USD", "hour")),
        ("$120k - $150k", Salary(120000, 150000, "USD", None)),
        ("4-6k USD monthly", Salary(4000, 6000, "USD", "month")),
        ("CA$90,000 - CA$110,000 / year", Salary(90000, 110000, "CAD", "year")),
    ],
)
def test_parse_salary(text: str, expected: Salary) -> None:
    assert parse_salary(text) == expected


@pytest.mark.parametrize(
    "text", [None, "", "Competitive", "Rs. 200,000 per month", "$80k - $60k", "DOE"]
)
def test_parse_salary_not_confident(text: str | None) -> None:
    assert parse_salary(text) is None


def test_to_usd_month() -> None:
    assert to_usd_month(120000, "USD", "year") == pytest.approx(10000)
    assert to_usd_month(5000, "USD", "month") == pytest.approx(5000)
    assert to_usd_month(50, "USD", "hour") == pytest.approx(50 * 40 * 52 / 12)
    pkr = fx_table().rates["PKR"]
    assert to_usd_month(pkr * 1000, "PKR", "month") == pytest.approx(1000)
    assert to_usd_month(100, "USD", None) is None
    assert to_usd_month(100, None, "month") is None
    assert to_usd_month(100, "XYZ", "month") is None


def test_fx_table_has_as_of_and_usd() -> None:
    t = fx_table()
    assert t.as_of
    assert t.rates["USD"] == 1.0
