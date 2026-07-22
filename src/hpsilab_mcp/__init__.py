"""Python SDK for H|ψ⟩ Quantum Finance APIs."""

from importlib.metadata import PackageNotFoundError, version


def _load_version() -> str:
    try:
        return version("hpsilab-mcp")
    except PackageNotFoundError:
        return "0.0.0"


# Computed before importing .client: client.py reads __version__ back off this
# package for its User-Agent / tracking headers, and that import would be
# circular (partially-initialized module) if it ran before this is set.
__version__ = _load_version()

from .client import HpsiMcpClient
from .errors import (
    HpsiMcpAPIError,
    HpsiMcpAuthError,
    HpsiMcpConnectionError,
    HpsiMcpError,
    HpsiMcpPaymentError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
    HpsiMcpTimeoutError,
)

__all__ = [
    "HpsiMcpAPIError",
    "HpsiMcpAuthError",
    "HpsiMcpClient",
    "HpsiMcpConnectionError",
    "HpsiMcpError",
    "HpsiMcpPaymentError",
    "HpsiMcpRateLimitError",
    "HpsiMcpResponseError",
    "HpsiMcpTimeoutError",
    "__version__",
]
