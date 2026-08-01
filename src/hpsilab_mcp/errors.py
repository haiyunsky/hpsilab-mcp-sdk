"""Error classes for the H|ψ⟩ Quantum Finance SDK."""

from __future__ import annotations

from typing import Optional


class HpsiMcpError(Exception):
    """Base exception for SDK errors."""


class HpsiMcpConnectionError(HpsiMcpError):
    """Raised when a request fails before the API returns a response."""


class HpsiMcpTimeoutError(HpsiMcpConnectionError):
    """Raised when an API request times out."""


class HpsiMcpAPIError(HpsiMcpError):
    """Raised when the API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        body: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        # The parsed response body, verbatim - backend is the single source
        # of truth for the error contract (docs/429-401-error-contract-spec.md);
        # named attributes on subclasses below promote the common fields for
        # convenience, but `body` guarantees nothing the backend sent is lost,
        # including anything added server-side after this SDK version shipped.
        self.body = body or {}


class HpsiMcpAuthError(HpsiMcpAPIError):
    """Raised when the API rejects authentication or authorization (401/403).

    For a 401 with no credentials sent at all, the backend's registration
    nudge survives as `register_url`/`pricing_url`/`upgrade_message` (see
    backend/app/dependencies/auth.py::NotAuthenticatedError) - all three are
    `None` for every other 401/403, including an expired token, by design
    (docs/429-401-error-contract-spec.md section 2.1: a real account holder
    with a stale token should not be pitched a signup link). `body` carries
    the complete raw response either way.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        body: Optional[dict] = None,
        register_url: Optional[str] = None,
        pricing_url: Optional[str] = None,
        upgrade_message: Optional[str] = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_text=response_text, body=body)
        self.register_url = register_url
        self.pricing_url = pricing_url
        self.upgrade_message = upgrade_message


class HpsiMcpPaymentError(HpsiMcpAPIError):
    """Raised on HTTP 402 — the call is available, but it has to be paid for.

    The API answers 402 when an anonymous caller has used up the free quota for
    a tool (or asks for a Pro tool, which has no anonymous allowance). The
    x402 challenge is attached so a caller can pay without re-parsing the body:

    * ``accepts`` — the payment options, each with scheme/network/asset/amount.
    * ``tool`` / ``price`` — which tool, and its price as a display string.

    Configure ``HpsiMcpClient(wallet=...)`` to sign and retry automatically;
    otherwise pay `accepts` with your own x402 client and resend the request
    with the resulting payment header.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        accepts: Optional[list] = None,
        tool: Optional[str] = None,
        price: Optional[str] = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_text=response_text)
        self.accepts = accepts or []
        self.tool = tool
        self.price = price


class HpsiMcpRateLimitError(HpsiMcpAPIError):
    """Raised on HTTP 429 — rate limited, or a daily/monthly quota is
    exhausted.

    Every business field the backend's 429 body carries is promoted onto
    this exception (docs/429-401-error-contract-spec.md section 1.2), so a
    caller does not have to re-parse `response_text`/`body` for the common
    ones:

    * ``tool`` — which tool's quota was hit, when the 429 is tool-scoped.
    * ``limit`` / ``window`` — the numeric cap and its reset window
      (``"day"``, ``"month"``, or ``"minute"``).
    * ``register_url`` / ``pricing_url`` / ``upgrade_message`` — the
      registration/upgrade nudge, normalized from either shape the backend
      may send (the nested ``upgrade.{register_url,pricing_url,message}`` or
      the flat ``register``/``upgrade_hint`` fallback).
    * ``register`` / ``upgrade_hint`` — those same flat strings, unmodified,
      in case a caller wants the backend's exact original values rather than
      the normalized URL/message split above.

    `body` still carries the complete raw response for anything not promoted
    to a named attribute here.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        body: Optional[dict] = None,
        tool: Optional[str] = None,
        limit: Optional[int] = None,
        window: Optional[str] = None,
        register_url: Optional[str] = None,
        pricing_url: Optional[str] = None,
        upgrade_message: Optional[str] = None,
        register: Optional[str] = None,
        upgrade_hint: Optional[str] = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_text=response_text, body=body)
        self.tool = tool
        self.limit = limit
        self.window = window
        self.register_url = register_url
        self.pricing_url = pricing_url
        self.upgrade_message = upgrade_message
        self.register = register
        self.upgrade_hint = upgrade_hint


class HpsiMcpResponseError(HpsiMcpAPIError):
    """Raised when the API response cannot be decoded as expected."""
