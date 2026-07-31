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
from .payments import X402Wallet, wallet_from_env
from .tracking import build_tracking_headers


DEFAULT_BASE_URL = "https://hpsilab.com"

# Header that opts an un-keyed caller into the backend's anonymous read-only
# path. Must match the backend's MCP_ANONYMOUS_READONLY_HEADER.
ANONYMOUS_READONLY_HEADER = "x-mcp-anonymous-readonly"

# The backend issues an anonymous caller a free key on its first *successful*
# response and repeats it in the body of the 429 that ends its daily pool.
# Presenting that key raises the pool substantially, so the client adopts it
# automatically — see `HpsiMcpClient.anon_key`.
ANON_KEY_HEADER = "x-hpsilab-anon-key"

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
        wallet: Optional[X402Wallet] = None,
        anon_key: Optional[str] = None,
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
            if anon_key:
                # A key kept from an earlier process. Sent alongside the
                # read-only header, not instead of it: this is still anonymous
                # traffic, it is just identifiable anonymous traffic.
                request_headers["Authorization"] = f"Bearer {anon_key}"

        self._api_key = api_key
        # Tracked separately from `_api_key`, which stays the user's own
        # credential: an anonymous key is something the server handed us, and
        # the two must never be confused when deciding whether to adopt a new
        # one or how to describe a rate-limit error.
        self._anon_key = anon_key if api_key is None else None
        # Pay-per-call is opt-in: an explicit wallet, or HPSILAB_X402_PRIVATE_KEY
        # in the environment. Without one a 402 is raised, never auto-paid.
        self._wallet = wallet if wallet is not None else wallet_from_env()
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=request_headers,
            timeout=timeout,
            transport=transport,
        )

    @property
    def anon_key(self) -> Optional[str]:
        """The free anonymous key this client is using, if any.

        Populated automatically the first time the server issues one. Persist
        it and pass it back as `anon_key=` in a later process to keep the
        larger daily allowance instead of starting over as an unidentified
        caller — the key is not tied to your IP address, which matters because
        cloud egress addresses drift.

        None for a client constructed with a real `api_key`: an account's
        credential is never displaced by an anonymous one.
        """
        return self._anon_key

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
        """Deprecated plural alias of `get_equity_curve`, kept for one release."""
        warnings.warn(
            "get_equity_curves() is deprecated; use get_equity_curve().",
            DeprecationWarning,
            stacklevel=2,
        )
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

    def register_account(self, email: str, adopt_key: bool = True) -> Any:
        """Register a free account for this caller and receive an API key.

        For agents: no password, no wallet, no web form. The account is also
        bound to this caller server-side, so calls made afterwards are metered
        as the account even from a process that cannot change its own
        Authorization header.

        The account starts unverified, which keeps the anonymous daily
        allowance until the emailed link is confirmed; confirming it unlocks
        the full Free plan.

        Idempotent: calling again returns the same account and a fresh key,
        rather than creating a second one. Raises `HpsiMcpAPIError` (409) if
        the address already belongs to a different account.

        `adopt_key=False` returns the response without switching this client
        over to the new key — use it when you intend to keep calling
        anonymously, or to hand the key to a different process.
        """
        response = self._send(
            "POST",
            "/api/agent/register",
            params=None,
            tool_name="register_account",
            json={"email": email},
        )
        self._raise_for_status(response)
        payload = self._decode_json(response)

        if adopt_key and isinstance(payload, dict):
            key = (payload.get("api_key") or "").strip()
            if key:
                # A real account key, so the anonymous one is now obsolete —
                # clearing it keeps `anon_key` an honest answer to "what
                # anonymous identity is in play", which is None from here on.
                self._api_key = key
                self._anon_key = None
                self._client.headers["Authorization"] = f"Bearer {key}"
        return payload

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
        return self._request("GET", path, params=params, tool_name=tool_name)

    def _post(
        self,
        path: str,
        params: Optional[Mapping[str, str]] = None,
        tool_name: Optional[str] = None,
    ) -> Any:
        return self._request("POST", path, params=params, tool_name=tool_name)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, str]] = None,
        tool_name: Optional[str] = None,
    ) -> Any:
        response = self._send(method, path, params, tool_name)
        adopted = self._adopt_anon_key(response)

        # A 429 that came with a key we did not have is the anonymous pool
        # running out *and* the fix arriving in the same response. Adopting it
        # and repeating the call once turns that dead end into a served
        # request; the retry is bounded by `adopted`, which can only be true
        # the first time, so an exhausted keyed caller still fails normally.
        if response.status_code == 429 and adopted:
            response = self._send(method, path, params, tool_name)
            self._adopt_anon_key(response)

        # 402 means "this call is available, it just costs money now". With a
        # wallet configured, sign the challenge and repeat the request once;
        # without one, fall through to _raise_for_status and hand the caller
        # the challenge to pay however they like.
        if response.status_code == 402 and self._wallet is not None:
            payment_headers = self._wallet.payment_headers(response)
            if payment_headers:
                response = self._send(method, path, params, tool_name, extra=payment_headers)

        self._raise_for_status(response)
        return self._decode_json(response)

    def _adopt_anon_key(self, response: httpx.Response) -> bool:
        """Pick up a server-issued anonymous key and use it from now on.

        Returns True only when a *new* key was adopted, so callers can use that
        to authorise exactly one retry.

        Skipped entirely for a client built with a real `api_key`: that
        caller's plan is already better than any anonymous allowance, and
        silently swapping its credential would be astonishing behaviour.

        The key arrives on a header for a served call and additionally in the
        JSON body of the 429 that ends the free pool, because an agent that
        only ever reads the body would otherwise never see it.
        """
        if self._api_key is not None:
            return False

        key = response.headers.get(ANON_KEY_HEADER)
        if not key and response.status_code == 429:
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                candidate = body.get("anon_key")
                if isinstance(candidate, str):
                    key = candidate

        key = (key or "").strip()
        if not key or key == self._anon_key:
            return False

        self._anon_key = key
        self._client.headers["Authorization"] = f"Bearer {key}"
        return True

    def _send(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, str]],
        tool_name: Optional[str],
        extra: Optional[Mapping[str, str]] = None,
        json: Optional[Mapping[str, Any]] = None,
    ) -> httpx.Response:
        headers = self._tool_headers(tool_name) or {}
        if extra:
            headers = {**headers, **extra}
        try:
            return self._client.request(
                method, path, params=params, json=json, headers=headers or None
            )
        except httpx.TimeoutException as exc:
            raise HpsiMcpTimeoutError("Request timed out.") from exc
        except httpx.RequestError as exc:
            raise HpsiMcpConnectionError("Request failed before a response was received.") from exc

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
            error = self._payment_error(message, response)
            if self._api_key is None:
                self._warn_anon_payment_required(error.price)
            raise error
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

    def _payment_error(self, message: str, response: httpx.Response) -> HpsiMcpPaymentError:
        """Attach the x402 challenge to the raised error.

        The body of a 402 is the challenge document, so pull `accepts` (and the
        tool/price hpsilab adds alongside it) onto the exception — a caller
        paying with their own x402 client shouldn't have to re-parse
        `response_text` to find out what was being asked for. A body that isn't
        the expected shape degrades to a plain payment error, never a decode
        crash on top of the original failure.
        """
        accepts = tool = price = None
        try:
            body = response.json()
            if isinstance(body, dict):
                raw_accepts = body.get("accepts")
                accepts = raw_accepts if isinstance(raw_accepts, list) else None
                tool = body.get("tool")
                price = body.get("price")
        except ValueError:
            pass

        if self._wallet is None:
            # Ordered by what the caller can actually do from here. A wallet
            # cannot be acquired mid-traceback — configuring one means editing
            # code and holding USDC — whereas `register_account` is a method on
            # the object that just raised, needs no wallet and no browser, and
            # is the only option that resolves this within the running process.
            message = (
                f"{message} To continue without a wallet, register free from "
                'this process: client.register_account(email="you@example.com").'
            )
            if price:
                message = (
                    f"{message} Or pay {price} per call by configuring "
                    "HpsiMcpClient(wallet=X402Wallet(...))."
                )
        return HpsiMcpPaymentError(
            message,
            status_code=response.status_code,
            response_text=response.text,
            accepts=accepts,
            tool=tool,
            price=price,
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

    def _warn_anon_payment_required(self, price: Optional[str]) -> None:
        """Surface the wallet-free way out of a 402 to the human running this.

        A 402 is where an anonymous caller's free allowance ends for good, so
        it is the moment the nudge matters most — and it is the one moment the
        429 nudge below never reaches, because `_raise_for_status` branches on
        402 first. Without this, crossing into overage *silences* the only
        human-visible prompt the SDK has, leaving a traceback recommending a
        crypto wallet as the script's entire output. Server-side message
        wording cannot fix that: nothing on this path reads it.

        Named as a method call rather than a URL on purpose. A URL needs a
        person with a browser; `register_account` is on the object that just
        raised, and resolves this inside the running process. Same unified
        copy as `_warn_anon_rate_limited` and the backend/mcp_server
        `_SIMPLE_QUOTA_MESSAGE` — the wallet price still rides along on the
        raised `HpsiMcpPaymentError`, it just isn't repeated in this text.
        """
        warnings.warn(
            'hpsilab: Free API key required. Register at https://hpsilab.com/register, '
            'or call client.register_account(email="you@example.com"). '
            "Pay-per-call details are on the raised HpsiMcpPaymentError.",
            stacklevel=3,
        )

    def _warn_anon_rate_limited(self, response: httpx.Response) -> None:
        """Surface the register nudge to a human, since an anonymous caller's
        script is likely only checking status codes and would otherwise never
        see the friendly message buried in the JSON body. Uses the standard
        warnings module so Python's default filter dedups identical warnings
        per process — no manual "already shown" state.

        Same unified copy regardless of whether this caller already holds an
        anonymous key (`self._anon_key`) — see
        backend/app/middleware/rate_limit.py::_SIMPLE_QUOTA_MESSAGE. Only the
        register URL is still read from the response body, since that value
        can move server-side without a new SDK release.
        """
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
            f"hpsilab: Free API key required. Register at {register_url}, "
            'or call client.register_account(email="you@example.com").',
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
