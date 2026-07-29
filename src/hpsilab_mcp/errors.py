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
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class HpsiMcpAuthError(HpsiMcpAPIError):
    """Raised when the API rejects authentication or authorization."""


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
    """Raised when the API returns a rate-limit response."""


class HpsiMcpResponseError(HpsiMcpAPIError):
    """Raised when the API response cannot be decoded as expected."""
