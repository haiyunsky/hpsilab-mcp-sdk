"""Synchronous REST client for H|ψ⟩ Quantum Finance APIs."""

from __future__ import annotations

import warnings
from types import TracebackType
from typing import Any, Mapping, Optional, Sequence, Type
from urllib.parse import quote

import httpx

from . import __version__
from .errors import (
    HpsiMcpAPIError,
    HpsiMcpAuthError,
    HpsiMcpConnectionError,
    HpsiMcpPaymentError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
    HpsiMcpTimeoutError,
)
from .tracking import build_tracking_headers


DEFAULT_BASE_URL = "https://hpsilab.com"

# Header that opts an un-keyed caller into the backend's anonymous read-only
# path. Must match the backend's MCP_ANONYMOUS_READONLY_HEADER.
ANONYMOUS_READONLY_HEADER = "x-mcp-anonymous-readonly"

_TRACKING_SOURCE = "sdk"
_TRACKING_CLIENT = "python-sdk"
_USER_AGENT = f"hpsilab-python-sdk/{__version__}"


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
        # Tracking headers first (defaults), caller-supplied headers layered on
        # top, then the business headers (Authorization / anonymous-readonly)
        # set last so they can never be clobbered by either of the above.
        request_headers = build_tracking_headers(
            source=_TRACKING_SOURCE,
            client=_TRACKING_CLIENT,
            version=__version__,
        )
        request_headers["User-Agent"] = _USER_AGENT
        request_headers.update(headers or {})
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

    def get_ai_prediction(self, symbol: str) -> Any:
        return self._get(f"/api/ai_prediction/{self._path_symbol(symbol)}", tool_name="get_ai_prediction")

    def analyze_stock(self, symbol: str, refresh: bool = False) -> Any:
        return self._get(
            f"/api/analyze_stock/{self._path_symbol(symbol)}",
            params=self._query_params(refresh=refresh),
            tool_name="analyze_stock",
        )

    def get_iv_radar(self, symbol: str) -> Any:
        return self._get(
            "/api/iv_batch",
            params={"symbols": self._clean_symbol(symbol)},
            tool_name="get_iv_radar",
        )

    def get_option_pressure(self, symbol: str) -> Any:
        return self._get(f"/api/option_pressure/{self._path_symbol(symbol)}", tool_name="get_option_pressure")

    def get_pretrade_risk_scan(self, symbol: str) -> Any:
        return self._get(
            f"/api/pretrade-risk-scan",
            params={"symbol": self._clean_symbol(symbol)},
            tool_name="get_pretrade_risk_scan",
        )

    def get_equity_curve(self, symbol: str) -> Any:
        return self._get(f"/api/equity_curve/{self._path_symbol(symbol)}", tool_name="get_equity_curve")

    def get_equity_curves(self, symbol: str) -> Any:
        return self.get_equity_curve(symbol)

    def get_monte_carlo(self, symbol: str) -> Any:
        return self._get(f"/api/monte_carlo/{self._path_symbol(symbol)}", tool_name="get_monte_carlo")

    def generate_stock_images(
        self,
        symbol: str,
        force: bool = False,
        types: Optional[Sequence[str]] = None,
    ) -> Any:
        return self._post(
            f"/api/stock_report/{self._path_symbol(symbol)}/images",
            params=self._query_params(force=force, types=self._join_types(types)),
            tool_name="generate_stock_images",
        )

    def generate_stock_research_report(
        self,
        symbol: str,
        refresh: bool = False,
        force_images: bool = False,
    ) -> Any:
        return self._post(
            f"/api/stock_report/{self._path_symbol(symbol)}/research_report",
            params=self._query_params(refresh=refresh, force_images=force_images),
            tool_name="generate_stock_research_report",
        )

    def _tool_headers(self, tool_name: Optional[str]) -> Optional[dict]:
        """Per-request override merged on top of the client's default headers
        (see `build_tracking_headers`) — only `X-HPSILAB-Tool` varies per call,
        the rest (source/client/version/User-Agent/Authorization/...) stay put."""
        if not tool_name:
            return None
        return build_tracking_headers(
            source=_TRACKING_SOURCE,
            client=_TRACKING_CLIENT,
            version=__version__,
            tool=tool_name,
        )

    def _get(
        self,
        path: str,
        params: Optional[Mapping[str, str]] = None,
        tool_name: Optional[str] = None,
    ) -> Any:
        try:
            response = self._client.get(path, params=params, headers=self._tool_headers(tool_name))
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
        tool_name: Optional[str] = None,
    ) -> Any:
        try:
            response = self._client.post(path, params=params, headers=self._tool_headers(tool_name))
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
            if self._api_key is None:
                self._warn_anon_rate_limited(response)
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
            # `message`/`error_message` are the human-readable sentences the
            # backend writes for this failure; `detail` is FastAPI's default
            # key for simple HTTPException bodies (401/403/...); `error` is a
            # last-resort fallback since it's often just a machine code (e.g.
            # "rate_limit_exceeded") rather than something meant for display.
            detail = data.get("message") or data.get("error_message") or data.get("detail") or data.get("error")
            if isinstance(detail, str) and detail:
                return detail
        return f"API request failed with status {response.status_code}."

    def _warn_anon_rate_limited(self, response: httpx.Response) -> None:
        """Surface the register/upgrade nudge to a human, since an anonymous
        caller's script is likely only checking status codes and would
        otherwise never see the friendly message buried in the JSON body.
        Uses the standard warnings module so Python's default filter dedups
        identical warnings per process — no manual "already shown" state."""
        register_url = "https://hpsilab.com/register"
        try:
            body = response.json()
            if isinstance(body, dict):
                upgrade = body.get("upgrade")
                if isinstance(upgrade, dict):
                    candidate = upgrade.get("register_url")
                    if isinstance(candidate, str) and candidate:
                        register_url = candidate
        except ValueError:
            pass
        warnings.warn(
            f"hpsilab: anonymous rate limit hit. Register free for a higher "
            f"quota: {register_url}",
            stacklevel=3,
        )

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
