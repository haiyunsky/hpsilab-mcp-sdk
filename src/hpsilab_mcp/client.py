"""Synchronous REST client for H|ψ⟩ Quantum Finance APIs."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Mapping, Optional, Sequence, Type
from urllib.parse import quote

import httpx

from .errors import (
    HpsiMcpAPIError,
    HpsiMcpAuthError,
    HpsiMcpConnectionError,
    HpsiMcpPaymentError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
    HpsiMcpTimeoutError,
)


DEFAULT_BASE_URL = "https://hpsilab.com"

# Tool tiers — the single source of truth lives in the backend (HTTP 402), but
# the SDK mirrors the catalog so Pro tools fail fast client-side with a clear
# message instead of a wasted round-trip. Free + freemium tools work without an
# API key (anonymous read-only); Pro tools require a paid `hpsi_…` key.
PRO_TOOLS = frozenset(
    {
        "get_ai_prediction",
        "get_equity_curve",
        "get_equity_curves",
        "generate_stock_images",
        "generate_stock_research_report",
    }
)

# Header that opts an un-keyed caller into the backend's anonymous read-only
# free-trial path (free + freemium tools). Must match the backend's
# MCP_ANONYMOUS_READONLY_HEADER.
ANONYMOUS_READONLY_HEADER = "x-mcp-anonymous-readonly"


class HpsiMcpClient:
    """Minimal REST API wrapper for the hosted H|ψ⟩ Quantum Finance APIs."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        headers: Optional[Mapping[str, str]] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        request_headers = dict(headers or {})
        if api_key:
            request_headers["Authorization"] = f"Bearer {api_key}"
        else:
            # No key → anonymous free-trial tier. Opt into the backend's
            # read-only path so free/freemium tools work without an account.
            request_headers.setdefault(ANONYMOUS_READONLY_HEADER, "1")

        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=request_headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HpsiMcpClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()

    def _guard_pro(self, tool: str) -> None:
        """Fail fast (no network call) when a Pro tool is used without a key."""
        if tool in PRO_TOOLS and not self._api_key:
            raise HpsiMcpPaymentError(
                f"{tool} is a Pro tool. Set api_key with a paid plan — "
                "upgrade at hpsilab.com/pricing.",
                status_code=402,
            )

    def get_ai_prediction(self, symbol: str) -> Any:
        self._guard_pro("get_ai_prediction")
        return self._get(f"/api/ai_prediction/{self._path_symbol(symbol)}")

    def analyze_stock(self, symbol: str, refresh: bool = False) -> Any:
        return self._get(
            f"/api/analyze_stock/{self._path_symbol(symbol)}",
            params=self._query_params(refresh=refresh),
        )

    def get_iv_radar(self, symbol: str) -> Any:
        return self._get("/api/iv_batch", params={"symbols": self._clean_symbol(symbol)})

    def get_option_pressure(self, symbol: str) -> Any:
        return self._get(f"/api/option_pressure/{self._path_symbol(symbol)}")

    def get_equity_curve(self, symbol: str) -> Any:
        self._guard_pro("get_equity_curve")
        return self._get(f"/api/equity_curve/{self._path_symbol(symbol)}")

    def get_equity_curves(self, symbol: str) -> Any:
        return self.get_equity_curve(symbol)

    def get_monte_carlo(self, symbol: str) -> Any:
        return self._get(f"/api/monte_carlo/{self._path_symbol(symbol)}")

    def generate_stock_images(
        self,
        symbol: str,
        force: bool = False,
        types: Optional[Sequence[str]] = None,
    ) -> Any:
        self._guard_pro("generate_stock_images")
        return self._post(
            f"/api/stock_report/{self._path_symbol(symbol)}/images",
            params=self._query_params(force=force, types=self._join_types(types)),
        )

    def generate_stock_research_report(
        self,
        symbol: str,
        refresh: bool = False,
        force_images: bool = False,
    ) -> Any:
        self._guard_pro("generate_stock_research_report")
        return self._post(
            f"/api/stock_report/{self._path_symbol(symbol)}/research_report",
            params=self._query_params(refresh=refresh, force_images=force_images),
        )

    def _get(
        self,
        path: str,
        params: Optional[Mapping[str, str]] = None,
    ) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise HpsiMcpTimeoutError("Request timed out.") from exc
        except httpx.RequestError as exc:
            raise HpsiMcpConnectionError("Request failed before a response was received.") from exc

        self._raise_for_status(response)
        return self._decode_json(response)

    def _post(
        self,
        path: str,
        params: Optional[Mapping[str, str]] = None,
    ) -> Any:
        try:
            response = self._client.post(path, params=params)
        except httpx.TimeoutException as exc:
            raise HpsiMcpTimeoutError("Request timed out.") from exc
        except httpx.RequestError as exc:
            raise HpsiMcpConnectionError("Request failed before a response was received.") from exc

        self._raise_for_status(response)
        return self._decode_json(response)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        message = self._error_message(response)
        if response.status_code in {401, 403}:
            raise HpsiMcpAuthError(
                message,
                status_code=response.status_code,
                response_text=response.text,
            )
        if response.status_code == 402:
            raise HpsiMcpPaymentError(
                message,
                status_code=response.status_code,
                response_text=response.text,
            )
        if response.status_code == 429:
            raise HpsiMcpRateLimitError(
                message,
                status_code=response.status_code,
                response_text=response.text,
            )
        raise HpsiMcpAPIError(
            message,
            status_code=response.status_code,
            response_text=response.text,
        )

    def _decode_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise HpsiMcpResponseError(
                "API response was not valid JSON.",
                status_code=response.status_code,
                response_text=response.text,
            ) from exc

    def _error_message(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return f"API request failed with status {response.status_code}."

        if isinstance(data, dict):
            detail = data.get("detail") or data.get("error") or data.get("message")
            if isinstance(detail, str) and detail:
                return detail
        return f"API request failed with status {response.status_code}."

    def _path_symbol(self, symbol: str) -> str:
        return quote(self._clean_symbol(symbol), safe="")

    def _clean_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise TypeError("Symbol must be a string.")
        cleaned = symbol.strip()
        if not cleaned:
            raise ValueError("Symbol is required.")
        return cleaned

    def _join_types(self, types: Optional[Sequence[str]]) -> Optional[str]:
        if types is None:
            return None
        cleaned = [item.strip() for item in types if item.strip()]
        return ",".join(cleaned) if cleaned else None

    def _query_params(self, **values: object) -> dict[str, str]:
        params: dict[str, str] = {}
        for key, value in values.items():
            if value is None:
                continue
            if isinstance(value, bool):
                params[key] = "true" if value else "false"
            else:
                params[key] = str(value)
        return params
