import pytest

from backend.api.middleware.rate_limiter import rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Keep the in-memory rate limiter from bleeding counts across tests."""
    rate_limiter._counts.clear()
    yield
    rate_limiter._counts.clear()
