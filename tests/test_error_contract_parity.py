"""The SDK's half of the cross-layer refusal contract.

Same samples as the backend and MCP server, read from
`contracts/error_contract_fixtures.json` in the monorepo. The SDK is its own
git repository, so a standalone checkout has no fixtures and these skip — the
consistency they check only exists where all four layers do.

The SDK's vocabulary is exception types, and the mapping below is the whole
point: a caller writes `except HpsiMcpRateLimitError: sleep()` and
`except HpsiMcpInsufficientCreditsError: top_up()`, so getting the type wrong
sends a program down a remedy that cannot work.
"""
from __future__ import annotations

import json
from pathlib import Path

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

FIXTURES_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "error_contract_fixtures.json"
)

# Exception type -> canonical kind. `HpsiMcpConfigError` is the SDK's way of
# saying "this client cannot authenticate as configured", which is the
# `unauthorized` kind expressed as a circuit breaker.
EXCEPTION_TO_KIND = {
    HpsiMcpConfigError: "unauthorized",
    HpsiMcpInsufficientCreditsError: "insufficient_credits",
    HpsiMcpPaymentError: "payment_challenge",
    HpsiMcpAuthError: "forbidden",
    HpsiMcpRateLimitError: "rate_limited",
}


def load_fixtures() -> list[dict]:
    if not FIXTURES_PATH.exists():  # pragma: no cover - standalone checkout
        return []
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["fixtures"]


FIXTURES = load_fixtures()
IDS = [f["name"] for f in FIXTURES]

pytestmark = pytest.mark.skipif(
    not FIXTURES, reason=f"shared fixtures not present at {FIXTURES_PATH}"
)


def _raise_for(fixture: dict) -> BaseException:
    """Drive one fixture through the real client and return what it raised.

    A fresh client per fixture: the auth circuit breaker is per-instance and
    latches, so a reused client would report the previous fixture's verdict.
    """
    response = httpx.Response(
        fixture["http_status"],
        json=fixture["body"],
        headers=fixture.get("headers") or {},
    )
    client = HpsiMcpClient(
        api_key="hpsi_test_key",
        transport=httpx.MockTransport(lambda request: response),
    )
    with pytest.raises(Exception) as caught:  # noqa: PT011 - the type is the assertion
        client.get_monte_carlo("NVDA")
    return caught.value


def _kind_of(error: BaseException) -> str | None:
    # Exact type, not isinstance: HpsiMcpInsufficientCreditsError and
    # HpsiMcpPaymentError both subclass HpsiMcpAPIError, and an isinstance walk
    # would happily report a subclass as its parent's kind.
    return EXCEPTION_TO_KIND.get(type(error))


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_the_sdk_raises_the_type_the_contract_agreed_on(fixture):
    error = _raise_for(fixture)

    assert _kind_of(error) == fixture["expect"]["kind"], (
        f"{fixture['name']}: SDK raised {type(error).__name__}, "
        f"contract says {fixture['expect']['kind']}"
    )


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_only_rate_limiting_tells_a_caller_to_wait(fixture):
    error = _raise_for(fixture)
    advertises_wait = getattr(error, "retry_after_seconds", None) is not None

    assert advertises_wait is fixture["expect"]["retryable"], (
        f"{fixture['name']}: {type(error).__name__} "
        f"retry_after_seconds={getattr(error, 'retry_after_seconds', None)}"
    )


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_only_a_settleable_offer_carries_payment_options(fixture):
    """`accepts` on the exception is what a wallet-holding caller settles. It
    must be present exactly when there is something to pay."""
    error = _raise_for(fixture)
    accepts = getattr(error, "accepts", None)

    assert bool(accepts) is fixture["expect"]["may_pay_with_x402"], (
        f"{fixture['name']}: accepts={accepts!r}"
    )


def test_running_out_of_credits_does_not_disable_the_client():
    """The credential is fine and adding Credits fixes it, so the client must
    stay usable — a latched breaker would fail every later call without ever
    reaching the network, including the ones made after topping up."""
    fixture = next(f for f in FIXTURES if f["name"] == "insufficient_credits")
    response = httpx.Response(fixture["http_status"], json=fixture["body"])
    client = HpsiMcpClient(
        api_key="hpsi_test_key",
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(HpsiMcpInsufficientCreditsError):
        client.get_monte_carlo("NVDA")

    assert client._auth_failed is False


def test_a_long_retry_after_is_never_raised_as_a_credits_problem():
    fixture = next(f for f in FIXTURES if f["name"] == "rate_limited_long_retry")
    error = _raise_for(fixture)

    assert isinstance(error, HpsiMcpRateLimitError)
    assert not isinstance(error, HpsiMcpInsufficientCreditsError)
