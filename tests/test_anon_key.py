"""Tests for the mandatory-identity constructor guard.

Anonymous free access was retired (mandatory-API-key plan): `HpsiMcpClient()`
now requires either a real `api_key` or a configured `wallet` before it will
even construct. This file used to test automatic adoption of a
server-issued anonymous key — that flow (and the header it rode on) no
longer exists, since the backend never issues one to the MCP/SDK channel
anymore. What's still meaningful from the old behavior — the 402/429 warning
text, malformed-body handling — is kept below, adapted to a real-account or
wallet-only client instead of an anonymous one.
"""
import warnings

import httpx
import pytest

from hpsilab_mcp import HpsiMcpClient, HpsiMcpConfigError, HpsiMcpRateLimitError

_PAYLOAD = {"ticker": "AAPL", "mean_price": 1.0}


class _FakeWallet:
    """Stands in for X402Wallet — the real one requires the optional [x402]
    extra and a valid EVM private key just to construct, neither of which
    this file's tests need. Only `payment_headers` is ever called on it."""

    def payment_headers(self, response):
        return {"X-PAYMENT": "signed-payload"}


def _client(handler, **kwargs):
    return HpsiMcpClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _ok():
    return httpx.Response(200, json=_PAYLOAD)


def _quota_exceeded():
    body = {
        "error": "tool_quota_exceeded",
        "message": "Free API key required. Register at https://hpsilab.com/register",
        "upgrade": {"register_url": "https://hpsilab.com/register"},
    }
    return httpx.Response(429, json=body)


def test_construction_with_neither_api_key_nor_wallet_raises():
    with pytest.raises(HpsiMcpConfigError):
        HpsiMcpClient(base_url="http://testserver")


def test_construction_with_only_an_api_key_succeeds():
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return _ok()

    with _client(handler, api_key="hpsi_real_account_key") as client:
        client.get_monte_carlo("AAPL")

    assert seen == ["Bearer hpsi_real_account_key"]


def test_construction_with_only_a_wallet_succeeds():
    def handler(request):
        return _ok()

    # No api_key at all — the wallet alone satisfies the constructor guard.
    with _client(handler, wallet=_FakeWallet()) as client:
        result = client.get_monte_carlo("AAPL")

    assert result == _PAYLOAD


def test_no_client_ever_sends_the_retired_anonymous_readonly_header():
    seen_headers = []

    def handler(request):
        seen_headers.append(dict(request.headers))
        return _ok()

    with _client(handler, api_key="hpsi_real_account_key") as client:
        client.get_monte_carlo("AAPL")

    assert "x-mcp-anonymous-readonly" not in seen_headers[0]


def test_malformed_429_body_does_not_crash_the_error_path():
    def handler(request):
        return httpx.Response(429, content=b"not json at all")

    with _client(handler, api_key="hpsi_real_account_key") as client:
        with pytest.raises(HpsiMcpRateLimitError):
            client.get_monte_carlo("AAPL")


def test_a_wallet_only_caller_gets_the_unified_quota_warning_on_429():
    """A wallet-only client (no api_key) can still hit a plain 429 — the
    PAID_RPM burst ceiling, not the retired anonymous quota pool. The warning
    still fires: `self._api_key is None` now means exactly "wallet-only",
    which is precisely the caller this nudge is for."""

    def handler(request):
        return _quota_exceeded()

    with _client(handler, wallet=_FakeWallet()) as client:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(HpsiMcpRateLimitError):
                client.get_monte_carlo("AAPL")

    text = str(caught[-1].message)
    assert "Free API key required" in text
    assert "hpsilab.com/register" in text
