"""Tests for agent self-registration.

The point of the feature is that an agent completes the anonymous -> account
transition unattended, so the cases that matter are the ones where a caller
gets a *worse* identity than it started with: a failed registration that
clobbered the working anonymous key, or a success the client didn't switch to.
"""
import json

import httpx
import pytest

from hpsilab_mcp import HpsiMcpAPIError, HpsiMcpClient

ANON_KEY = "hpsi_anon_" + "a" * 48
ACCOUNT_KEY = "hpsi_" + "z" * 43


def _client(handler, **kwargs):
    return HpsiMcpClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _registered(already=False, key=ACCOUNT_KEY):
    return httpx.Response(
        200,
        json={
            "user_id": 1,
            "email": "agent@example.com",
            "tier": "free",
            "email_verified": False,
            "api_key": key,
            "already_registered": already,
            "message": "Registered.",
        },
    )


def test_registers_and_returns_the_account():
    def handler(request):
        assert request.url.path == "/api/agent/register"
        assert request.method == "POST"
        assert json.loads(request.content) == {"email": "agent@example.com"}
        return _registered()

    result = _client(handler).register_account("agent@example.com")

    assert result["api_key"] == ACCOUNT_KEY
    assert result["already_registered"] is False


def test_client_switches_to_the_new_account_key():
    """Otherwise the caller registers and then keeps calling anonymously —
    the one outcome that makes the whole feature pointless."""
    seen = []

    def handler(request):
        seen.append(request.headers.get("Authorization"))
        if request.url.path == "/api/agent/register":
            return _registered()
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    client.register_account("agent@example.com")
    client.get_monte_carlo("NVDA")

    assert seen[-1] == f"Bearer {ACCOUNT_KEY}"
    # `anon_key` must stop claiming an anonymous identity that is no longer used.
    assert client.anon_key is None


def test_adopt_key_false_leaves_the_caller_anonymous():
    def handler(request):
        if request.url.path == "/api/agent/register":
            return _registered()
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, anon_key=ANON_KEY)
    result = client.register_account("agent@example.com", adopt_key=False)

    assert result["api_key"] == ACCOUNT_KEY
    assert client.anon_key == ANON_KEY


def test_email_collision_raises_and_keeps_the_existing_identity():
    """A 409 means the address belongs to someone else. The caller must be left
    exactly as it was, still holding its working anonymous key."""
    def handler(request):
        return httpx.Response(409, json={"detail": "That email is already registered."})

    client = _client(handler, anon_key=ANON_KEY)
    with pytest.raises(HpsiMcpAPIError) as exc:
        client.register_account("someone-else@example.com")

    assert exc.value.status_code == 409
    assert client.anon_key == ANON_KEY


def test_repeat_registration_is_reported_as_already_registered():
    client = _client(lambda request: _registered(already=True))
    assert client.register_account("agent@example.com")["already_registered"] is True


def test_registration_carries_the_tool_tracking_header():
    seen = {}

    def handler(request):
        seen["tool"] = request.headers.get("X-HPSILAB-Tool")
        return _registered()

    _client(handler).register_account("agent@example.com")
    assert seen["tool"] == "register_account"
