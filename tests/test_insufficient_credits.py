"""Credits refusals must be distinguishable from every other 402, 403 and 429.

The backend returns `insufficient_credits` on **402**. That status is shared with
the x402 pay-per-call challenge, and this client *settles* challenges — it hands
the body to a configured wallet and retries. So the shared status creates two
ways to get this badly wrong, and both were live before this contract:

1. **The wallet path.** A refusal has no `accepts`, so a wallet asked to sign one
   raises, which trips the authentication circuit breaker and reports an empty
   balance as a permanently broken client that has to be reconstructed.
2. **The breaker itself.** `_raise_for_status` trips it for every 401/402. An
   empty balance is not an authentication failure: the key is valid, and the call
   made after a top-up must reach the network.

The legacy **403** form is still recognised — SDK and API version independently,
and a caller may be pointed at either.
"""
from __future__ import annotations

import httpx
import pytest

from hpsilab_mcp import (
    HpsiMcpAuthError,
    HpsiMcpClient,
    HpsiMcpConfigError,
    HpsiMcpInsufficientCreditsError,
    HpsiMcpPaymentError,
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

_ANON_REFUSAL = {
    **_REFUSAL,
    "register": "https://hpsilab.com/register",
    "upgrade_hint": "Upgrade at https://hpsilab.com/pricing",
}

# What an actual x402 challenge looks like: an offer, with options to settle.
_CHALLENGE = {
    "x402Version": 2,
    "error": "Payment required",
    "accepts": [{"scheme": "exact", "network": "eip155:8453", "maxAmountRequired": "100000"}],
    "tool": "get_monte_carlo",
    "price": "$0.10",
}


class _RecordingWallet:
    """Stands in for X402Wallet (the real one needs the optional [x402] extra).

    Records whether it was asked to pay, which is the assertion that matters: a
    Credits refusal must never reach it.
    """

    def __init__(self) -> None:
        self.calls = 0

    def payment_headers(self, response: httpx.Response) -> dict:
        self.calls += 1
        return {"X-PAYMENT": "signed"}


def _client(response: httpx.Response, **kwargs) -> HpsiMcpClient:
    return HpsiMcpClient(
        api_key=_KEY,
        transport=httpx.MockTransport(lambda request: response),
        **kwargs,
    )


def test_a_402_credits_refusal_raises_its_own_error():
    client = _client(httpx.Response(402, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    error = caught.value
    assert error.credits_required == 30
    assert error.credits_remaining == 12
    assert error.upgrade_url == "https://hpsilab.com/pricing"
    assert error.status_code == 402


def test_the_legacy_403_form_is_still_understood():
    """Same body, older status — a mixed-version deployment must not make the
    caller see two different problems."""
    client = _client(httpx.Response(403, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    assert caught.value.credits_required == 30
    assert caught.value.status_code == 403


def test_a_refusal_is_never_handed_to_the_wallet():
    """The refusal carries no `accepts`, so there is nothing to sign. Asking the
    wallet anyway is what turned "out of Credits" into an unrecoverable client."""
    wallet = _RecordingWallet()
    client = _client(httpx.Response(402, json=_REFUSAL), wallet=wallet)

    with pytest.raises(HpsiMcpInsufficientCreditsError):
        client.get_monte_carlo("NVDA")

    assert wallet.calls == 0


def test_a_real_challenge_is_still_paid():
    """The other 402. A wallet-configured client must keep settling these, or
    disambiguating the two statuses has broken pay-per-call."""
    wallet = _RecordingWallet()
    responses = [httpx.Response(402, json=_CHALLENGE), httpx.Response(200, json={"ok": True})]
    client = HpsiMcpClient(
        api_key=_KEY,
        wallet=wallet,
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
    )

    assert client.get_monte_carlo("NVDA") == {"ok": True}
    assert wallet.calls == 1


def test_a_402_refusal_does_not_trip_the_auth_breaker():
    """An empty balance is not a bad credential: the key is fine and the call made
    after a top-up must go out, not be short-circuited locally forever."""
    client = _client(httpx.Response(402, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError):
        client.get_monte_carlo("NVDA")

    assert client._auth_failed is False


def test_the_client_still_works_once_credits_are_added():
    """The end-to-end consequence of the breaker staying closed."""
    responses = [httpx.Response(402, json=_REFUSAL), httpx.Response(200, json={"ok": True})]
    client = HpsiMcpClient(
        api_key=_KEY,
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
    )

    with pytest.raises(HpsiMcpInsufficientCreditsError):
        client.get_monte_carlo("NVDA")

    assert client.get_monte_carlo("NVDA") == {"ok": True}


def test_it_is_not_a_rate_limit_error():
    """Waiting fixes a rate limit. Waiting never refills a balance, so a caller
    that treats the two alike sits in a retry loop forever."""
    client = _client(httpx.Response(402, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    assert not isinstance(caught.value, HpsiMcpRateLimitError)


def test_it_is_not_a_payment_error():
    """`HpsiMcpPaymentError` means "an offer is attached"; acting on this one that
    way sends the caller looking for a wallet it does not need."""
    client = _client(httpx.Response(402, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    assert not isinstance(caught.value, HpsiMcpPaymentError)
    assert not isinstance(caught.value, HpsiMcpConfigError)


def test_an_anonymous_refusal_offers_registration():
    """Registering is free and is the cheaper remedy — the API only sends
    `register` to a caller that has not taken it."""
    client = _client(httpx.Response(402, json=_ANON_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    assert caught.value.register_url == "https://hpsilab.com/register"


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


def test_a_402_with_no_body_is_still_handled():
    """Not a Credits refusal (no body says so), so it keeps the old unpayable-402
    behaviour rather than being misreported as an empty balance."""
    client = _client(httpx.Response(402, content=b"not json at all"))

    with pytest.raises(HpsiMcpConfigError):
        client.get_monte_carlo("NVDA")


def test_the_error_message_reaches_a_human():
    client = _client(httpx.Response(402, json=_REFUSAL))

    with pytest.raises(HpsiMcpInsufficientCreditsError) as caught:
        client.get_monte_carlo("NVDA")

    assert "Credits" in str(caught.value)


def test_a_429_still_carries_what_a_bounded_retry_needs():
    """The mirror image: a rate limit must stay retryable, and must say for how
    long, or "bounded retry" has nothing to bound itself with."""
    client = HpsiMcpClient(
        api_key=_KEY,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                429,
                json={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests (10/min).",
                    "limit": 10,
                    "window": "minute",
                    "retry_after_seconds": 23,
                    "reset_at": "2026-08-08T00:00:23+00:00",
                },
                headers={"Retry-After": "23"},
            )
        ),
    )

    with pytest.raises(HpsiMcpRateLimitError) as caught:
        client.get_monte_carlo("NVDA")

    error = caught.value
    assert error.retry_after_seconds == 23
    assert error.reset_at == "2026-08-08T00:00:23+00:00"
    assert error.window == "minute"
    assert error.limit == 10
    assert not isinstance(error, HpsiMcpInsufficientCreditsError)


def test_a_429_without_the_header_falls_back_to_the_body():
    client = HpsiMcpClient(
        api_key=_KEY,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                429,
                json={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests.",
                    "retry_after_seconds": 7,
                },
            )
        ),
    )

    with pytest.raises(HpsiMcpRateLimitError) as caught:
        client.get_monte_carlo("NVDA")

    assert caught.value.retry_after_seconds == 7
