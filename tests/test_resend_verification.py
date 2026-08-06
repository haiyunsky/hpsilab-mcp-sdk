"""Tests for resend_verification_email() — what a bound-but-unverified
caller's 429 (backend/app/middleware/rate_limit.py::_pool_quota_response,
bound_account=True) actually points at. The old message pointed at
https://hpsilab.com/settings, a page with no such feature; this method wraps
the endpoint that's actually reachable without a browser session.
"""
import httpx
import pytest

from hpsilab_mcp import HpsiMcpClient, HpsiMcpConfigError, HpsiMcpRateLimitError

ACCOUNT_KEY = "hpsi_" + "z" * 43


class _FakeWallet:
    def payment_headers(self, response):
        return {"X-PAYMENT": "signed-payload"}


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
    # A wallet-only client has no account to verify (a construction with
    # neither api_key nor wallet can't even get this far — see
    # HpsiMcpClient.__init__ — so a wallet is what stands in for "no account
    # key" here). No Authorization header ever goes out, so the backend's
    # response is the same plain 401 any other authenticated-only endpoint
    # would give it — no special-casing needed on either side.
    client = HpsiMcpClient(
        base_url="http://testserver",
        wallet=_FakeWallet(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"detail": "Not authenticated"})
        ),
    )

    with pytest.raises(HpsiMcpConfigError):
        client.resend_verification_email()
