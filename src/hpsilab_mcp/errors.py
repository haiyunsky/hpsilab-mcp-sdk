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
    """Raised when a Pro-tier tool is called without a paid plan (HTTP 402)."""


class HpsiMcpRateLimitError(HpsiMcpAPIError):
    """Raised when the API returns a rate-limit response."""


class HpsiMcpResponseError(HpsiMcpAPIError):
    """Raised when the API response cannot be decoded as expected."""
