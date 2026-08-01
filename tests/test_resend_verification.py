"""Tests for resend_verification_email() — what a bound-but-unverified
caller's 429 (backend/app/middleware/rate_limit.py::_pool_quota_response,
bound_account=True) actually points at. The old message pointed at
https://hpsilab.com/settings, a page with no such feature; this method wraps
the endpoint that's actually reachable without a browser session.
"""
import httpx
import pytest

from hpsilab_mcp import HpsiMcpAuthError, HpsiMcpClient, HpsiMcpRateLimitError

ACCOUNT_KEY = "hpsi_" + "z" * 43


def _client(handler, **kwargs):
    return HpsiMcpClient(
        base_url="http://testserver",
        api_key=ACCOUNT_KEY,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_resend_verification_posts_to_the_right_endpoint_with_the_account_key():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"email_verified": False, "email": "agent@example.com"})

    result = _client(handler).resend_verification_email()

    assert seen["method"] == "POST"
    assert seen["path"] == "/api/auth/resend-verification"
    assert seen["authorization"] == f"Bearer {ACCOUNT_KEY}"
    assert result["email_verified"] is False


def test_resend_verification_cooldown_raises_rate_limit_error():
    def handler(request):
        return httpx.Response(
            429, json={"detail": "Please wait a moment before requesting another email."}
        )

    with pytest.raises(HpsiMcpRateLimitError) as exc:
        _client(handler).resend_verification_email()

    assert "wait a moment" in str(exc.value)


def test_resend_verification_without_an_account_key_raises_auth_error():
    # An anonymous caller has no account to verify - same failure any other
    # authenticated endpoint would give it, no special-casing needed.
    client = HpsiMcpClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"detail": "Not authenticated"})
        ),
    )

    with pytest.raises(HpsiMcpAuthError):
        client.resend_verification_email()
