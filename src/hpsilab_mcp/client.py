"""Synchronous REST client for H|ψ⟩ Quantum Finance APIs."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Mapping, Optional, Type
from urllib.parse import quote

import httpx

from .errors import (
    HpsiMcpAPIError,
    HpsiMcpAuthError,
    HpsiMcpConnectionError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
    HpsiMcpTimeoutError,
)


DEFAULT_BASE_URL = "https://hpsilab.com"


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
        return self._get(f"/api/ai_prediction/{self._path_symbol(symbol)}")

    def get_iv_radar(self, symbol: str) -> Any:
        return self._get("/api/iv_batch", params={"symbols": self._clean_symbol(symbol)})

    def get_option_pressure(self, symbol: str) -> Any:
        return self._get(f"/api/option_pressure/{self._path_symbol(symbol)}")

    def get_equity_curve(self, symbol: str) -> Any:
        return self._get(f"/api/equity_curve/{self._path_symbol(symbol)}")

    def get_equity_curves(self, symbol: str) -> Any:
        return self.get_equity_curve(symbol)

    def get_monte_carlo(self, symbol: str) -> Any:
        return self._get(f"/api/monte_carlo/{self._path_symbol(symbol)}")

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
