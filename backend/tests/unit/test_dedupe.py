from app.discovery.dedupe import is_near_duplicate

JD = (
    "We are hiring a backend engineer to build our payments platform with Python, FastAPI and "
    "Postgres. You will design APIs, own services end to end, and work with product and design "
    "partners every day. Requirements: 4+ years of backend experience, strong SQL, experience "
    "with distributed systems, queues, caching, observability, and on-call ownership of the "
    "services you ship. Nice to have: Kubernetes, Terraform, and experience in fintech."
)


def test_identical_text_is_duplicate() -> None:
    assert is_near_duplicate(JD, JD)


def test_small_edit_is_duplicate() -> None:
    edited = JD.replace("Nice to have", "Bonus points")
    assert is_near_duplicate(JD, edited)


def test_different_jd_is_not_duplicate() -> None:
    other = "We need a designer to own our brand, illustrations, and marketing site. " * 3
    assert not is_near_duplicate(JD, other)
