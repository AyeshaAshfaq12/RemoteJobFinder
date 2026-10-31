"""Near-duplicate rules (Build Spec section 6). Exact matching is the jobs_dedupe unique index;
title trigram similarity runs in Postgres (pg_trgm); JD similarity runs here."""

from app.discovery.normalize import jaccard, shingles

NEAR_TITLE_SIMILARITY = 0.9
NEAR_JD_JACCARD = 0.85


def is_near_duplicate(jd_a: str, jd_b: str, threshold: float = NEAR_JD_JACCARD) -> bool:
    """3-shingle Jaccard similarity of the normalized JDs above the threshold."""
    return jaccard(shingles(jd_a), shingles(jd_b)) > threshold
