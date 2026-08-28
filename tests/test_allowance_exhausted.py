"""The allowance refusal must survive as attributes, not just as a raw body.

`HpsiMcpAllowanceExhaustedError` promotes the remedy onto the exception so a
caller writes `exc.verify_email_url` instead of re-parsing `exc.body`. That
only helps if the promotion actually keeps the value: the URL allowlist used
to admit `/register` and `/pricing` and nothing else, and the backend sends the
site root as `verify_email` — so every unverified caller got `None` for the one
remedy that applies to it, and consumers reading the attribute lost the link
while the body still carried it.

Bodies here mirror the `allowance_exhausted_*` fixtures in the monorepo's
`contracts/error_contract_fixtures.json`, trimmed to the fields these
assertions read. `tests/test_error_contract_parity.py` checks the real
fixtures where the monorepo is present; this file holds in a standalone
checkout, where those skip.
"""

from __future__ import annotations

import httpx
import pytest

from hpsilab_mcp import HpsiMcpAllowanceExhaustedError, HpsiMcpClient
from hpsilab_mcp.errors import safe_public_url

_KEY = "hpsi_test_key"

_UNVERIFIED = {
    "error": "anonymous_allowance_exhausted",
    "message": (
        "Registered access is 1000 calls per 7 days and 1004 have been used "
        "(cached results count too). Verify your email to move to the Free "
        "plan - click the link in the signup email, or resend it free from "
        "https://hpsilab.com/."
    ),
    "calls_used": 1004,
    "calls_allowed": 1000,
    "window_days": 7,
    "upgrade_url": "https://hpsilab.com/pricing",
    "credits_charged": 0,
    "verify_email": "https://hpsilab.com/",
    "email_verified": False,
    "tool": "get_monte_carlo",
    "next_actions": [
        {
            "type": "verify_email",
            "label": "Verify your email to move to the Free plan",
            "url": "https://hpsilab.com/",
        }
    ],
}

_ANONYMOUS = {
    "error": "anonymous_allowance_exhausted",
    "message": "Anonymous access is 300 calls per 7 days and 301 have been used.",
    "calls_used": 301,
    "calls_allowed": 300,
    "calls_allowed_next": 1000,
    "window_days": 7,
    "credits_charged": 0,
    "register": "https://hpsilab.com/register",
    "tool": "get_monte_carlo",
    "next_actions": [{"type": "register_account", "tool": "register_account"}],
}


def _client(response: httpx.Response) -> HpsiMcpClient:
    return HpsiMcpClient(
        api_key=_KEY,
        transport=httpx.MockTransport(lambda request: response),
    )


def test_an_unverified_caller_keeps_the_verification_link():
    client = _client(httpx.Response(402, json=_UNVERIFIED))

    with pytest.raises(HpsiMcpAllowanceExhaustedError) as caught:
        client.get_monte_carlo("NVDA")

    error = caught.value
    assert error.verify_email_url == "https://hpsilab.com/"
    # The attribute is the promoted form of the body field, so a caller that
    # reads one must not see less than a caller that reads the other.
    assert error.verify_email_url == error.body["verify_email"]
    assert error.register_url is None
    assert error.calls_used == 1004
    assert error.calls_allowed == 1000


def test_an_anonymous_caller_still_gets_registration_and_no_verify_link():
    """Widening the allowlist must not blur the two rungs: an unregistered
    caller registers, and has no email to verify."""
    client = _client(httpx.Response(402, json=_ANONYMOUS))

    with pytest.raises(HpsiMcpAllowanceExhaustedError) as caught:
        client.get_monte_carlo("NVDA")

    error = caught.value
    assert error.register_url == "https://hpsilab.com/register"
    assert error.verify_email_url is None
    assert error.calls_allowed_next == 1000


@pytest.mark.parametrize(
    "value",
    [
        "https://hpsilab.com/",
        "https://hpsilab.com",
        "https://hpsilab.com//",
        "https://hpsilab.com:443/",
    ],
)
def test_the_site_root_is_public_however_it_is_spelled(value):
    assert safe_public_url(value) == "https://hpsilab.com/"


def test_the_root_drops_query_and_fragment_like_every_other_allowed_path():
    """A resend link may arrive with a one-time token attached; the attribute
    is quoted in logs and tracebacks, so the token must not ride along."""
    assert (
        safe_public_url("https://hpsilab.com/?token=secret#sent")
        == "https://hpsilab.com/"
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://hpsilab.com/evil",
        "https://hpsilab.com/register/../evil",
        "http://hpsilab.com/",
        "https://evil.com/",
        "https://hpsilab.com.evil.com/",
        "https://hpsilab.com@evil.com/",
        "https://user:pw@hpsilab.com/",
        "https://hpsilab.com:8443/",
        "//hpsilab.com/",
        "javascript:alert(1)",
    ],
)
def test_admitting_the_root_admits_nothing_else(value):
    assert safe_public_url(value) is None
