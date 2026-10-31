"""Ghost-risk weights (Build Spec section 7). Tuned later from outcomes; never auto-changed."""

WEIGHTS: dict[str, int] = {
    "not_on_company_ats": 35,
    "repost_2plus_90d": 25,
    "repost_1_90d": 10,
    "age_over_45d": 15,
    "age_over_30d": 8,
    "company_shrinking": 15,
    "salary_listed": -10,
    "seen_by_many": -5,  # 3+ distinct users submitted it in the last 7 days
}

JD_FLAG_POINTS: dict[str, int] = {
    "no_responsibilities": 4,
    "no_team": 3,
    "talent_pool_wording": 6,
    "generic_template": 3,
    "named_hiring_contact": -5,
}
