"""Tests for agent self-registration: the standalone `register()` function
(no client instance needed — the entry point for a truly fresh caller, since
`HpsiMcpClient()` now requires an api_key or wallet to even construct) and
`HpsiMcpClient.register_account` (the instance method, for a caller that
already has an identity — typically wallet-only — and wants an account too).
"""
import json

import httpx
import pytest

import hpsilab_mcp
from hpsilab_mcp import HpsiMcpAPIError, HpsiMcpClient

ACCOUNT_KEY = "hpsi_" + "z" * 43


class _FakeWallet:
    def payment_headers(self, response):
        return {"X-PAYMENT": "signed-payload"}


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


# --------------------------------------------------------------------------- #
# Standalone hpsilab_mcp.register() — the fresh-caller entry point
# --------------------------------------------------------------------------- #


def test_register_returns_the_account_with_no_client_needed():
    def handler(request):
        assert request.url.path == "/api/agent/register"
        assert request.method == "POST"
        assert json.loads(request.content) == {"email": "agent@example.com"}
        return _registered()

    result = hpsilab_mcp.register(
        "agent@example.com", base_url="http://testserver", transport=httpx.MockTransport(handler)
    )

    assert result["api_key"] == ACCOUNT_KEY
    assert result["already_registered"] is False


def test_register_result_constructs_a_working_client():
    def handler(request):
        if request.url.path == "/api/agent/register":
            return _registered()
        assert request.headers.get("Authorization") == f"Bearer {ACCOUNT_KEY}"
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    result = hpsilab_mcp.register("agent@example.com", base_url="http://testserver", transport=transport)
    client = HpsiMcpClient(base_url="http://testserver", api_key=result["api_key"], transport=transport)

    assert client.get_monte_carlo("NVDA") == {"ok": True}
    client.close()


def test_register_email_collision_raises():
    def handler(request):
        return httpx.Response(409, json={"detail": "That email is already registered."})

    with pytest.raises(HpsiMcpAPIError) as exc:
        hpsilab_mcp.register(
            "someone-else@example.com", base_url="http://testserver", transport=httpx.MockTransport(handler)
        )

    assert exc.value.status_code == 409


def test_register_carries_the_tool_tracking_header():
    seen = {}

    def handler(request):
        seen["tool"] = request.headers.get("X-HPSILAB-Tool")
        return _registered()

    hpsilab_mcp.register("agent@example.com", base_url="http://testserver", transport=httpx.MockTransport(handler))

    assert seen["tool"] == "register_account"


# --------------------------------------------------------------------------- #
# HpsiMcpClient.register_account — an already-constructed client wants an
# account too (typically a wallet-only client that would rather stop paying
# per call within its free allowance)
# --------------------------------------------------------------------------- #


def test_registers_and_returns_the_account():
    def handler(request):
        assert request.url.path == "/api/agent/register"
        assert request.method == "POST"
        assert json.loads(request.content) == {"email": "agent@example.com"}
        return _registered()

    result = _client(handler, wallet=_FakeWallet()).register_account("agent@example.com")

    assert result["api_key"] == ACCOUNT_KEY
    assert result["already_registered"] is False


def test_client_switches_to_the_new_account_key():
    """Otherwise the caller registers and then keeps paying per call anyway —
    the one outcome that makes the whole feature pointless."""
    seen = []

    def handler(request):
        seen.append(request.headers.get("Authorization"))
        if request.url.path == "/api/agent/register":
            return _registered()
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, wallet=_FakeWallet())
    client.register_account("agent@example.com")
    client.get_monte_carlo("NVDA")

    assert seen[-1] == f"Bearer {ACCOUNT_KEY}"
    assert client._api_key == ACCOUNT_KEY


def test_adopt_key_false_leaves_the_wallet_only_identity_in_place():
    def handler(request):
        if request.url.path == "/api/agent/register":
            return _registered()
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, wallet=_FakeWallet())
    result = client.register_account("agent@example.com", adopt_key=False)

    assert result["api_key"] == ACCOUNT_KEY
    assert client._api_key is None


def test_email_collision_raises_and_keeps_the_existing_identity():
    """A 409 means the address belongs to someone else. The caller must be left
    exactly as it was, still holding its own account key."""
    def handler(request):
        return httpx.Response(409, json={"detail": "That email is already registered."})

    client = _client(handler, api_key="hpsi_existing_key")
    with pytest.raises(HpsiMcpAPIError) as exc:
        client.register_account("someone-else@example.com")

    assert exc.value.status_code == 409
    assert client._api_key == "hpsi_existing_key"


def test_repeat_registration_is_reported_as_already_registered():
    client = _client(lambda request: _registered(already=True), wallet=_FakeWallet())
    assert client.register_account("agent@example.com")["already_registered"] is True


def test_registration_carries_the_tool_tracking_header():
    seen = {}

    def handler(request):
        seen["tool"] = request.headers.get("X-HPSILAB-Tool")
        return _registered()

    _client(handler, wallet=_FakeWallet()).register_account("agent@example.com")
    assert seen["tool"] == "register_account"
