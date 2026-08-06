"""Error classes for the H|ψ⟩ Quantum Finance SDK."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit


_REDACTED = "[REDACTED]"
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "apikey",
        "accesstoken",
        "authorization",
        "clientsecret",
        "credential",
        "mnemonic",
        "paymentsignature",
        "privatekey",
        "recoveryphrase",
        "refreshtoken",
        "secret",
        "seedphrase",
        "xpayment",
    }
)
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|authorization|client[_-]?secret|"
        r"credential|private[_-]?key|mnemonic|refresh[_-]?token|secret|"
        r"seed[_-]?phrase|recovery[_-]?phrase|payment[_-]?signature|x[_-]?payment)"
        r"\b\s*[:=]\s*[\"']?[^,\s\"'}]+"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\bhpsi_[A-Za-z0-9_-]+"),
    re.compile(r"(?i)\b0x[0-9a-f]{64}\b"),
    re.compile(r"(?i)\b0x[0-9a-f]{40}\b"),
    re.compile(r"(?i)(https://hpsilab\.com/(?:register|pricing))(?:\?[^\s]+|#[^\s]+)"),
)


def redact_sensitive_text(value: str) -> str:
    """Remove credential and wallet-shaped values from diagnostic text."""
    redacted = value
    for pattern in _SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(r"\1" if pattern.groups else _REDACTED, redacted)
    return redacted


def sanitize_response_text(value: Optional[str]) -> Optional[str]:
    """Redact structured JSON responses as data and other text by pattern."""
    if value is None:
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return redact_sensitive_text(value)
    return json.dumps(sanitize_sensitive_data(decoded), ensure_ascii=False, separators=(",", ":"))


def sanitize_sensitive_data(value: Any) -> Any:
    """Return a detached, recursively redacted copy of response data."""
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            sanitized[key] = _REDACTED if normalized_key in _SENSITIVE_FIELD_NAMES else sanitize_sensitive_data(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_sensitive_data(item) for item in value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return deepcopy(value)


def safe_public_url(value: Optional[str], *, fallback: Optional[str] = None) -> Optional[str]:
    """Allow only public HPSILab HTTPS URLs and discard query secrets."""
    if not value:
        return fallback
    try:
        parsed = urlsplit(value)
    except ValueError:
        return fallback
    try:
        port = parsed.port
    except ValueError:
        return fallback
    if (
        parsed.scheme != "https"
        or parsed.hostname != "hpsilab.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.path.rstrip("/") not in {"/register", "/pricing"}
    ):
        return fallback
    return urlunsplit(("https", "hpsilab.com", parsed.path, "", ""))


class HpsiMcpError(Exception):
    """Base exception for SDK errors."""


class HpsiMcpConfigError(HpsiMcpError):
    """Raised when the client cannot make authenticated requests.

    This includes invalid construction (neither an API key nor a wallet) and
    the authentication circuit breaker opened by an unresolved HTTP 401/402.
    It remains a plain configuration signal rather than `HpsiMcpAPIError`;
    callers must reconfigure or replace the client before trying again.
    """


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
        super().__init__(redact_sensitive_text(message))
        self.status_code = status_code
        self.response_text = sanitize_response_text(response_text)
        # Preserve response context for callers while removing credentials,
        # payment signatures, private-key fields, and wallet-shaped values.
        self.body = sanitize_sensitive_data(body or {})


class HpsiMcpAuthError(HpsiMcpAPIError):
    """Raised when the API rejects authentication or authorization (401/403).

    For a 401 with no credentials sent at all, the backend's registration
    nudge survives as `register_url`/`pricing_url`/`upgrade_message` (see
    backend/app/dependencies/auth.py::NotAuthenticatedError) - all three are
    `None` for every other 401/403, including an expired token, by design
    (docs/429-401-error-contract-spec.md section 2.1: a real account holder
    with a stale token should not be pitched a signup link). `body` carries a
    recursively redacted copy of the response.
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
        self.register_url = safe_public_url(register_url)
        self.pricing_url = safe_public_url(pricing_url)
        self.upgrade_message = redact_sensitive_text(upgrade_message) if upgrade_message else None


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
        body: Optional[dict] = None,
        accepts: Optional[list] = None,
        tool: Optional[str] = None,
        price: Optional[str] = None,
    ) -> None:
        # Keep the complete challenge available to payment-aware callers, but
        # never fold it into Exception.args / str(exc). Tracebacks, SDK logs,
        # and ordinary console output therefore contain only `message`.
        super().__init__(message, status_code=status_code, response_text=response_text, body=body)
        self.accepts = sanitize_sensitive_data(accepts or [])
        self.tool = redact_sensitive_text(tool) if tool else None
        self.price = redact_sensitive_text(price) if price else None


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

    `body` carries the remaining response fields after recursive redaction.
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
        self.tool = redact_sensitive_text(tool) if tool else None
        self.limit = limit
        self.window = window
        self.register_url = safe_public_url(register_url)
        self.pricing_url = safe_public_url(pricing_url)
        self.upgrade_message = redact_sensitive_text(upgrade_message) if upgrade_message else None
        self.register = safe_public_url(register)
        self.upgrade_hint = redact_sensitive_text(upgrade_hint) if upgrade_hint else None


class HpsiMcpResponseError(HpsiMcpAPIError):
    """Raised when the API response cannot be decoded as expected."""
