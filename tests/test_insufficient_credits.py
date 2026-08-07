"""Credits refusals must be distinguishable from every other 403 and 429.

The backend returns `insufficient_credits` on **403**, because 402 is the x402
challenge (this client tries to settle those on-chain) and 429 is forbidden for
it by design. That leaves one status carrying two meanings — "your plan lacks
this tool" and "your balance is empty" — which need opposite reactions from a
caller. These tests pin down that the SDK tells them apart, and that a caller
never ends up retrying against an empty account.
"""
from __future__ import annotations

import httpx
import pytest

from hpsilab_mcp import (
    HpsiMcpAuthError,
    HpsiMcpClient,
    HpsiMcpInsufficientCreditsError,
    HpsiMcpRateLimitError,
)

_KEY = "hpsi_test_key"

_REFUSAL = {
    "error": "insufficient_credits",
    "credits_required": 30,
    "credits_remaining": 12,
    "upgrade_url": "https://hpsilab.com/pricing",
    "message": "This call costs 30 Credits and 12 remain.",
    "request_id": "req-42",
}


def _client(response: httpx.Response) -> HpsiMcpClient:
    return HpsiMcpClient(
        api_key=_KEY,
        transport=httpx.MockTransport(lambda request: response),
    )


def test_a_credits_refusal_raises_its_own_error():
    client = _client(httpx.Response(403, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    error = caught.value
    assert error.credits_required == 30
    assert error.credits_remaining == 12
    assert error.upgrade_url == "https://hpsilab.com/pricing"
    assert error.status_code == 403


def test_it_is_not_a_rate_limit_error():
    """Waiting fixes a rate limit. Waiting never refills a balance, so a caller
    that treats the two alike sits in a retry loop forever."""
    client = _client(httpx.Response(403, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    assert not isinstance(caught.value, HpsiMcpRateLimitError)


def test_an_ordinary_403_still_raises_the_plan_error():
    """The other meaning of 403 must keep its own error, or "upgrade your plan"
    and "add Credits" become the same message."""
    client = _client(
        httpx.Response(403, json={"error": "tool_not_in_plan", "tool": "get_monte_carlo"})
    )

    with pytest.raises(HpsiMcpAuthError) as caught:
        client.get_monte_carlo("NVDA")

    assert not isinstance(caught.value, HpsiMcpInsufficientCreditsError)


def test_a_403_with_no_body_does_not_crash_the_client():
    client = _client(httpx.Response(403, content=b"not json at all"))

    with pytest.raises(HpsiMcpAuthError):
        client.get_monte_carlo("NVDA")


def test_the_error_message_reaches_a_human():
    client = _client(httpx.Response(403, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    assert "Credits" in str(caught.value)


def test_a_refusal_does_not_trip_the_auth_breaker():
    """An empty balance is not a bad credential: the key is fine and the next
    call after a top-up must go out, not be short-circuited locally."""
    client = _client(httpx.Response(403, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError):
        client.get_monte_carlo("NVDA")

    assert client._auth_failed is False
