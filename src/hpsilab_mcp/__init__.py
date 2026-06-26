"""Python SDK for H|ψ⟩ Quantum Finance APIs."""

from importlib.metadata import PackageNotFoundError, version

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


def _load_version() -> str:
    try:
        return version("hpsilab-mcp")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _load_version()

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
