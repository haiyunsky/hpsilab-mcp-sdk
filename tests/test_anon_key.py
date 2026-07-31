"""Tests for automatic adoption of the server-issued anonymous key.

Without this the SDK is the one channel that cannot participate in the
anonymous-identity flow at all: the backend issues the key on a response
*header*, and the SDK hands its caller only the decoded JSON body.
"""
import json
import warnings

import httpx
import pytest

from hpsilab_mcp import HpsiMcpClient, HpsiMcpRateLimitError
from hpsilab_mcp.client import ANON_KEY_HEADER, ANONYMOUS_READONLY_HEADER

KEY = "hpsi_anon_" + "a" * 48
OTHER_KEY = "hpsi_anon_" + "b" * 48
_PAYLOAD = {"ticker": "AAPL", "mean_price": 1.0}


def _client(handler, **kwargs):
    return HpsiMcpClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _ok(headers=None):
    return httpx.Response(200, json=_PAYLOAD, headers=headers or {})


def _pool_exhausted():
    body = {
        "error": "tool_quota_exceeded",
        "message": f"Anonymous daily limit reached (30 calls/day). ... 'Authorization: Bearer {KEY}'",
        "anon_key": KEY,
        "upgrade": {"register_url": "https://hpsilab.com/register"},
    }
    return httpx.Response(429, json=body)


def test_key_from_a_successful_response_is_adopted():
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return _ok({ANON_KEY_HEADER: KEY})

    with _client(handler) as client:
        assert client.anon_key is None
        client.get_monte_carlo("AAPL")
        assert client.anon_key == KEY
        client.get_monte_carlo("MSFT")

    assert seen[0] is None                      # first call was unidentified
    assert seen[1] == f"Bearer {KEY}"           # every later call carries it


def test_pool_exhausted_429_adopts_the_key_and_retries_once():
    calls = []

    def handler(request):
        calls.append(request.headers.get("authorization"))
        if len(calls) == 1:
            return _pool_exhausted()
        return _ok()

    with _client(handler) as client:
        result = client.get_monte_carlo("AAPL")

    # The dead end became a served call, which is the entire point.
    assert result == _PAYLOAD
    assert calls == [None, f"Bearer {KEY}"]


def test_an_exhausted_keyed_caller_still_fails_instead_of_looping():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return _pool_exhausted()

    with _client(handler, anon_key=KEY) as client:
        with pytest.raises(HpsiMcpRateLimitError):
            client.get_monte_carlo("AAPL")

    # Already had that key, so nothing new was adopted and nothing was retried.
    assert len(calls) == 1


def test_a_real_api_key_is_never_displaced_by_an_anonymous_one():
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return _ok({ANON_KEY_HEADER: KEY})

    with _client(handler, api_key="hpsi_real_account_key") as client:
        client.get_monte_carlo("AAPL")
        client.get_monte_carlo("MSFT")
        assert client.anon_key is None

    assert seen == ["Bearer hpsi_real_account_key"] * 2


def test_a_persisted_key_is_sent_from_the_first_call():
    seen = []

    def handler(request):
        seen.append(
            (request.headers.get("authorization"), request.headers.get(ANONYMOUS_READONLY_HEADER))
        )
        return _ok()

    with _client(handler, anon_key=KEY) as client:
        client.get_monte_carlo("AAPL")
        assert client.anon_key == KEY

    # Still anonymous traffic, just identifiable: both headers travel together.
    assert seen == [(f"Bearer {KEY}", "1")]


def test_a_rotated_key_replaces_the_old_one():
    responses = [_ok({ANON_KEY_HEADER: KEY}), _ok({ANON_KEY_HEADER: OTHER_KEY}), _ok()]
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return responses[len(seen) - 1]

    with _client(handler) as client:
        client.get_monte_carlo("A")
        client.get_monte_carlo("B")
        client.get_monte_carlo("C")
        assert client.anon_key == OTHER_KEY

    assert seen[2] == f"Bearer {OTHER_KEY}"


def test_malformed_429_body_does_not_crash_the_error_path():
    def handler(request):
        return httpx.Response(429, content=b"not json at all")

    with _client(handler) as client:
        with pytest.raises(HpsiMcpRateLimitError):
            client.get_monte_carlo("AAPL")


def test_keyed_caller_still_gets_the_unified_quota_warning():
    def handler(request):
        return _pool_exhausted()

    with _client(handler, anon_key=KEY) as client:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(HpsiMcpRateLimitError):
                client.get_monte_carlo("AAPL")

    text = str(caught[-1].message)
    assert "Free API key required" in text
    assert "hpsilab.com/register" in text
