"""Python SDK for H|ψ⟩ Quantum Finance APIs."""

from importlib.metadata import PackageNotFoundError, version


# Reported when the package is imported from a source tree rather than an
# installed distribution: vendored sources, `PYTHONPATH=src`, and some zip /
# PyInstaller bundles all leave `importlib.metadata` with nothing to read.
#
# It used to be a bare "0.0.0", which cost us the version but kept the signal
# ("this caller is running from source"). Carrying both is strictly better:
# the base must track pyproject's version — tests/test_version.py fails if it
# drifts — and the `+source` local segment keeps the two cases distinguishable
# in the request logs.
_FALLBACK_VERSION = "0.14.0+source"


def _load_version() -> str:
    try:
        return version("hpsilab-mcp")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


# Computed before importing .client: client.py reads __version__ back off this
# package for its User-Agent / tracking headers, and that import would be
# circular (partially-initialized module) if it ran before this is set.
__version__ = _load_version()

from .client import HpsiMcpClient, register
from .errors import (
    HpsiMcpAPIError,
    HpsiMcpAllowanceExhaustedError,
    HpsiMcpAuthError,
    HpsiMcpConfigError,
    HpsiMcpConnectionError,
    HpsiMcpError,
    HpsiMcpPaymentError,
    HpsiMcpRateLimitError,
    HpsiMcpInsufficientCreditsError,
    HpsiMcpResponseError,
    HpsiMcpSettlementUnknownError,
    HpsiMcpTimeoutError,
    HpsiMcpToolError,
    HpsiMcpValidationError,
)
from .payments import X402Wallet
from .mcp_result import McpDependencyMetadata, McpToolResult
from .policy import (
    CREDITS_ONLY,
    X402_FALLBACK,
    PaymentPolicy,
    PaymentPolicyError,
)

__all__ = [
    "CREDITS_ONLY",
    "PaymentPolicy",
    "PaymentPolicyError",
    "X402_FALLBACK",
    "HpsiMcpAPIError",
    "HpsiMcpAllowanceExhaustedError",
    "HpsiMcpAuthError",
    "HpsiMcpClient",
    "HpsiMcpConfigError",
    "HpsiMcpConnectionError",
    "HpsiMcpError",
    "HpsiMcpPaymentError",
    "HpsiMcpInsufficientCreditsError",
    "HpsiMcpRateLimitError",
    "HpsiMcpResponseError",
    "HpsiMcpSettlementUnknownError",
    "HpsiMcpTimeoutError",
    "HpsiMcpToolError",
    "HpsiMcpValidationError",
    "McpDependencyMetadata",
    "McpToolResult",
    "X402Wallet",
    "__version__",
    "register",
]
