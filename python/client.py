"""Lightweight Python SDK skeleton for H|ψ⟩ Quantum Finance MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping


class HpsiMcpError(RuntimeError):
    """Raised when an MCP tool call cannot be completed."""


@dataclass(slots=True)
class HpsiMcpClient:
    """Minimal client wrapper for H|ψ⟩ Quantum Finance MCP tool calls.

    This class is a transport-agnostic skeleton. Wire `_request` to the MCP
    transport used by your application, such as stdio, HTTP, or an SDK adapter.
    """

    server_url: str | None = None
    timeout_seconds: float = 30.0
    default_headers: MutableMapping[str, str] = field(default_factory=dict)

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        """Call an MCP tool by name.

        Args:
            name: MCP tool name, such as "analyze_stock".
            arguments: JSON-serializable tool arguments.

        Returns:
            The decoded tool response from the configured MCP transport.
        """

        if not name:
            raise ValueError("Tool name is required.")

        payload = {
            "tool": name,
            "arguments": dict(arguments or {}),
        }
        return self._request(payload)

    def get_ai_prediction(self, symbol: str) -> Any:
        return self.call_tool("get_ai_prediction", {"symbol": symbol})

    def get_iv_radar(self, symbol: str) -> Any:
        return self.call_tool("get_iv_radar", {"symbol": symbol})

    def get_option_pressure(self, symbol: str) -> Any:
        return self.call_tool("get_option_pressure", {"symbol": symbol})

    def get_equity_curves(self, symbol: str) -> Any:
        return self.call_tool("get_equity_curves", {"symbol": symbol})

    def get_monte_carlo(self, symbol: str) -> Any:
        return self.call_tool("get_monte_carlo", {"symbol": symbol})
    
    def analyze_stock(self, symbol: str) -> Any:
        return self.call_tool("analyze_stock", {"symbol": symbol})

    def generate_stock_images(self, symbol: str) -> Any:
        return self.call_tool("generate_stock_images", {"symbol": symbol})

    def generate_stock_research_report(self, symbol: str) -> Any:
        return self.call_tool(
            "generate_stock_research_report",
            {"symbol": symbol},
        )

    def _request(self, payload: Mapping[str, Any]) -> Any:
        """Send a request through your MCP transport.

        Replace this method with your chosen MCP client implementation. This
        skeleton intentionally contains no proprietary analytics or server logic.
        """

        raise NotImplementedError(
            "Connect this skeleton to an MCP transport before calling tools."
        )


__all__ = ["HpsiMcpClient", "HpsiMcpError"]
