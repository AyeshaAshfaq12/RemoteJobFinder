"""Salary parsing and USD-per-month conversion (Build Spec section 6).

The original currency and period are stored on the job; USD/month is computed only when
comparing against salary_floor_usd_month or displaying (decided 2026-10-29). Anything the
parser isn't confident about is left null.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

Period = Literal["hour", "day", "week", "month", "year"]

# Months-equivalent factors: 40 h/week, 52 weeks/year, ~21.67 working days/month.
_TO_MONTH: dict[str, float] = {
    "hour": 40 * 52 / 12,
    "day": 260 / 12,
    "week": 52 / 12,
    "month": 1.0,
    "year": 1 / 12,
}


@dataclass(frozen=True)
class FxTable:
    as_of: str
    rates: dict[str, float]


@lru_cache
def fx_table() -> FxTable:
    raw = json.loads((Path(__file__).parent / "fx_rates.json").read_text(encoding="utf-8"))
    return FxTable(as_of=raw["as_of"], rates={k: float(v) for k, v in raw["rates"].items()})


@dataclass(frozen=True)
class Salary:
    min: int
    max: int
    currency: str
    period: Period | None


_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("us$", "USD"),
    ("ca$", "CAD"),
    ("c$", "CAD"),
    ("au$", "AUD"),
    ("a$", "AUD"),
    ("nz$", "NZD"),
    ("s$", "SGD"),
    ("r$", "BRL"),
    ("$", "USD"),
    ("€", "EUR"),
    ("£", "GBP"),
    ("₹", "INR"),
)
_PERIODS: tuple[tuple[re.Pattern[str], Period], ...] = (
    (re.compile(r"/\s*h(?:ou)?r\b|\bper\s+hour\b|\bhourly\b|\ban\s+hour\b"), "hour"),
    (re.compile(r"/\s*day\b|\bper\s+day\b|\bdaily\b|\ba\s+day\b"), "day"),
    (re.compile(r"/\s*w(?:ee)?k\b|\bper\s+week\b|\bweekly\b"), "week"),
    (re.compile(r"/\s*mo(?:nth)?\b|\bper\s+month\b|\bmonthly\b|\bpm\b|\ba\s+month\b"), "month"),
    (
        re.compile(
            r"/\s*y(?:ea)?r\b|/\s*annum\b|\bper\s+(?:year|annum)\b|\bannual(?:ly)?\b|\byearly\b"
            r"|\bp\.?a\.?\b|\ba\s+year\b"
        ),
        "year",
    ),
)
_AMOUNT = re.compile(r"(\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([km])?\b", re.I)


def _currency(text: str) -> str | None:
    upper = text.upper()
    for code in fx_table().rates:
        if re.search(rf"(?<![A-Z]){code}(?![A-Z])", upper):
            return code
    lowered = text.lower()
    for symbol, code in _SYMBOLS:
        if symbol in lowered:
            return code
    return None


def _period(text: str) -> Period | None:
    lowered = text.lower()
    for pattern, period in _PERIODS:
        if pattern.search(lowered):
            return period
    return None


def _amounts(text: str) -> list[tuple[float, str | None]]:
    out: list[tuple[float, str | None]] = []
    for m in _AMOUNT.finditer(text):
        value = float(re.sub(r"[,\s]", "", m.group(1)))
        out.append((value, (m.group(2) or "").lower() or None))
    return out


def _scale(value: float, suffix: str | None) -> float:
    if suffix == "k":
        return value * 1_000
    if suffix == "m":
        return value * 1_000_000
    return value


def parse_salary(text: str | None) -> Salary | None:
    """'$4k-6k/month' -> Salary(4000, 6000, 'USD', 'month'). None when not confident."""
    if not text or not re.search(r"\d", text):
        return None
    currency = _currency(text)
    if currency is None:
        return None
    amounts = _amounts(text)
    if not amounts:
        return None
    (lo_v, lo_s) = amounts[0]
    if len(amounts) >= 2:
        hi_v, hi_s = amounts[1]
        # "4-6k": the suffix on the upper bound applies to the lower bound too.
        lo = _scale(lo_v, lo_s or hi_s)
        hi = _scale(hi_v, hi_s)
    else:
        lo = hi = _scale(lo_v, lo_s)
    if lo <= 0 or hi < lo:
        return None
    return Salary(min=round(lo), max=round(hi), currency=currency, period=_period(text))


def to_usd_month(amount: float, currency: str | None, period: str | None) -> float | None:
    if currency is None or period is None:
        return None
    rate = fx_table().rates.get(currency.upper())
    factor = _TO_MONTH.get(period)
    if rate is None or factor is None:
        return None
    return amount / rate * factor
