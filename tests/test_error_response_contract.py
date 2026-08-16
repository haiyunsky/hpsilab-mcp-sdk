"""Frozen HTTP-to-SDK exception mapping from docs/error-response-contract.md."""

import httpx
import pytest

from hpsilab_mcp import (
    HpsiMcpClient,
    HpsiMcpConfigError,
    HpsiMcpInsufficientCreditsError,
    HpsiMcpPaymentError,
    HpsiMcpRateLimitError,
)


def _client(status: int, body: dict, headers: dict | None = None) -> HpsiMcpClient:
    response = httpx.Response(status, json=body, headers=headers or {})
    return HpsiMcpClient(
        api_key="hpsi_contract_test",
        transport=httpx.MockTransport(lambda request: response),
    )


@pytest.mark.parametrize("body", [
    {"error": "not_authenticated", "detail": "Not authenticated"},
    {"detail": "Invalid or expired API key."},
])
def test_401_trips_authentication_not_payment_or_rate_limit(body):
    client = _client(401, body)

    with pytest.raises(HpsiMcpConfigError) as caught:
        client.get_monte_carlo("AAPL")

    assert not isinstance(caught.value, HpsiMcpPaymentError)
    assert not isinstance(caught.value, HpsiMcpRateLimitError)


def test_credits_402_raises_insufficient_credits_without_wait():
    client = _client(402, {
        "error": "insufficient_credits",
        "message": "This call costs 5 Credits and 1 remain.",
        "credits_required": 5,
        "credits_remaining": 1,
        "upgrade_url": "https://hpsilab.com/pricing",
    })

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("AAPL")

    assert caught.value.credits_required == 5
    assert caught.value.credits_remaining == 1
    assert not isinstance(caught.value, HpsiMcpRateLimitError)
    assert getattr(caught.value, "retry_after_seconds", None) is None
    assert client._auth_failed is False


def test_pure_x402_challenge_raises_payment_error():
    client = _client(402, {
        "x402Version": 2,
        "error": "X-PAYMENT header is required",
        "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "50000"}],
    })

    with pytest.raises(HpsiMcpPaymentError) as caught:
        client.get_monte_carlo("AAPL")

    assert caught.value.accepts
    assert not isinstance(caught.value, HpsiMcpInsufficientCreditsError)


def test_credits_402_with_offer_is_actionable_payment_in_current_sdk():
    client = _client(402, {
        "x402Version": 2,
        "error": "insufficient_credits",
        "message": "This call costs 5 Credits and 0 remain.",
        "credits_required": 5,
        "credits_remaining": 0,
        "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "50000"}],
    })

    with pytest.raises(HpsiMcpPaymentError) as caught:
        client.get_monte_carlo("AAPL")

    assert caught.value.accepts


def test_429_raises_rate_limit_and_prefers_retry_after_header():
    client = _client(429, {
        "error": "rate_limit_exceeded",
        "message": "Too many requests.",
        "limit": 60,
        "window": "minute",
        "retry_after_seconds": 7,
        "reset_at": "2026-08-16T00:00:42Z",
    }, {"Retry-After": "42"})

    with pytest.raises(HpsiMcpRateLimitError) as caught:
        client.get_monte_carlo("AAPL")

    assert caught.value.retry_after_seconds == 42
    assert not isinstance(caught.value, HpsiMcpInsufficientCreditsError)
