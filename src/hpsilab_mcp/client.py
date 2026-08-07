"""Synchronous REST client for H|ψ⟩ Quantum Finance APIs."""

from __future__ import annotations

import warnings
from threading import RLock
from types import TracebackType
from typing import Any, Mapping, Optional, Sequence, Type
from urllib.parse import quote

import httpx

from . import __version__
from .errors import (
    HpsiMcpAPIError,
    HpsiMcpAuthError,
    HpsiMcpInsufficientCreditsError,
    HpsiMcpConfigError,
    HpsiMcpConnectionError,
    HpsiMcpPaymentError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
    HpsiMcpTimeoutError,
    redact_sensitive_text,
    safe_public_url,
)
from .payments import X402Wallet, wallet_from_env
from .tracking import build_tracking_headers


DEFAULT_BASE_URL = "https://hpsilab.com"

_TRACKING_SOURCE = "sdk"
_TRACKING_CLIENT = "python-sdk"
_USER_AGENT = f"hpsilab-python-sdk/{__version__}"

_MISSING_AUTH_MESSAGE = """API key or wallet required.

Anonymous access has ended.

Free API key:
    hpsilab_mcp.register(email="you@example.com")

Or configure:
    api_key=
    wallet=
    HPSILAB_X402_PRIVATE_KEY"""

_REMOVE_AUTH_MESSAGE = """API key or wallet required.

The Client must keep at least one authentication method.

Configure:
    api_key=
    wallet=
    HPSILAB_X402_PRIVATE_KEY"""


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
    ) -> None:
        # Pay-per-call is opt-in: an explicit wallet, or HPSILAB_X402_PRIVATE_KEY
        # in the environment.
        resolved_wallet = wallet if wallet is not None else wallet_from_env()

        # Anonymous free access was retired (API key is mandatory) — x402
        # payment is the one remaining key-free path, so identity has to be
        # one or the other, checked before anything is constructed. A fresh
        # caller with neither should use the standalone `register()`
        # function (no client instance needed) to get a key first.
        if not api_key and resolved_wallet is None:
            raise HpsiMcpConfigError(_MISSING_AUTH_MESSAGE)

        # Tracking headers first (defaults), caller-supplied headers layered on
        # top, then the business header (Authorization) set last so it can
        # never be clobbered by either of the above.
        request_headers = build_tracking_headers(
            source=_TRACKING_SOURCE,
            client=_TRACKING_CLIENT,
            version=__version__,
        )
        request_headers["User-Agent"] = _USER_AGENT
        request_headers.update(headers or {})
        if api_key:
            request_headers["Authorization"] = f"Bearer {api_key}"

        self._api_key = api_key
        self._wallet = resolved_wallet
        self._auth_failed = False
        self._auth_failure_message: Optional[str] = None
        # Keep the check/request/response transition atomic. Without this,
        # concurrent calls could all leave the process before the first 401 or
        # unpayable 402 trips the breaker. An "out of Credits" 402 never trips
        # it — see `_raise_for_status`.
        self._request_lock = RLock()
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=request_headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __repr__(self) -> str:  # pragma: no cover - diagnostic safety
        api_key_state = "configured" if self._api_key else "not-configured"
        wallet_state = "configured" if self._wallet is not None else "not-configured"
        return f"<HpsiMcpClient api_key={api_key_state} wallet={wallet_state}>"

    def set_api_key(self, api_key: Optional[str]) -> None:
        """Replace the API key and reset this client's authentication breaker."""
        with self._request_lock:
            if not api_key and self._wallet is None:
                raise HpsiMcpConfigError(_REMOVE_AUTH_MESSAGE)
            self._api_key = api_key
            if api_key:
                self._client.headers["Authorization"] = f"Bearer {api_key}"
            else:
                self._client.headers.pop("Authorization", None)
            self._reset_auth_circuit()

    def set_wallet(self, wallet: Optional[X402Wallet]) -> None:
        """Replace the x402 wallet and reset this client's authentication breaker."""
        with self._request_lock:
            if wallet is None and not self._api_key:
                raise HpsiMcpConfigError(_REMOVE_AUTH_MESSAGE)
            self._wallet = wallet
            self._reset_auth_circuit()

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
        Authorization header. Works on any constructed client, including a
        wallet-only one (`HpsiMcpClient(wallet=...)`) that wants an account
        too — a fresh caller with no client yet should use the standalone
        `hpsilab_mcp.register()` function instead, since construction itself
        now requires an api_key or a wallet.

        The account starts unverified, which keeps the anonymous-rate daily
        allowance until the emailed link is confirmed; confirming it unlocks
        the full Free plan.

        Idempotent: calling again returns the same account and a fresh key,
        rather than creating a second one. Raises `HpsiMcpAPIError` (409) if
        the address already belongs to a different account.

        `adopt_key=False` returns the response without switching this client
        over to the new key — use it to keep this client on its current
        identity (e.g. a wallet-only client that wants to keep paying per
        call rather than switch to the account it just registered), or to
        hand the key to a different process.
        """
        with self._request_lock:
            self._ensure_auth_circuit_closed()
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
                    self.set_api_key(key)
        return payload

    def resend_verification_email(self) -> Any:
        """Ask the backend to re-send this account's verification email.

        Requires a real account key (passed as `api_key=` or adopted via
        `register_account()`). The backend no longer falls back to a
        fingerprint match for a header-less caller — API key is mandatory
        (mandatory-API-key plan retired that fallback along with the rest of
        anonymous MCP/SDK access, since fingerprint-binding was itself a
        no-key-needed identity). A caller that lost its key has to register
        again (`register_account()`/`hpsilab_mcp.register()`) rather than
        being silently recognized by IP/client fingerprint.

        This is what a caller's 429 (`HpsiMcpRateLimitError`) on Free-tier
        quota with an unverified email is pointing at: the account's
        allowance stays at the anonymous rate until the email is confirmed,
        and there is no signup step left to offer — verifying is the only
        lever.

        Raises `HpsiMcpRateLimitError` (429) if you already requested one
        recently — the backend enforces a short cooldown between resends.
        """
        with self._request_lock:
            self._ensure_auth_circuit_closed()
            response = self._send(
                "POST",
                "/api/auth/resend-verification",
                params=None,
                tool_name="resend_verification_email",
            )
            self._raise_for_status(response)
            return self._decode_json(response)

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
        with self._request_lock:
            self._ensure_auth_circuit_closed()
            response = self._send(method, path, params, tool_name)

            # A 402 is retryable exactly once, and only after a configured
            # wallet successfully produces payment headers.
            #
            # `not self._is_insufficient_credits(response)` is what keeps that
            # true now that the API answers "out of Credits" on 402 as well. That
            # body is not a payment offer — it has no `accepts` — so a wallet has
            # nothing to sign, and handing it one means `payment_headers` raises,
            # `_trip_auth_circuit` fires, and an empty balance is reported to the
            # caller as a permanently broken client that must be reconstructed.
            if (
                response.status_code == 402
                and self._wallet is not None
                and not self._is_insufficient_credits(response)
            ):
                try:
                    payment_headers = self._wallet.payment_headers(response)
                except Exception:
                    # Do not chain third-party wallet exceptions: a wallet
                    # implementation may include signed payment context in
                    # its exception text or attributes, which must not leak
                    # into user tracebacks or logs.
                    self._trip_auth_circuit(response)
                if payment_headers:
                    response = self._send(method, path, params, tool_name, extra=payment_headers)

            self._raise_for_status(response)
            return self._decode_json(response)

    def _reset_auth_circuit(self) -> None:
        self._auth_failed = False
        self._auth_failure_message = None

    def _ensure_auth_circuit_closed(self) -> None:
        if self._auth_failed:
            raise HpsiMcpConfigError(self._auth_failure_message or _MISSING_AUTH_MESSAGE)

    def _trip_auth_circuit(
        self,
        response: httpx.Response,
    ) -> None:
        message = f"""Authentication failed (HTTP {response.status_code}).

{redact_sensitive_text(self._error_message(response))}

Fix:
    client.set_api_key("NEW_API_KEY")
    client.set_wallet(wallet)
    or create a new HpsiMcpClient"""
        self._auth_failed = True
        self._auth_failure_message = message
        raise HpsiMcpConfigError(message) from None

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
        failure: Optional[str] = None
        try:
            response = self._client.request(
                method, path, params=params, json=json, headers=headers or None
            )
        except httpx.TimeoutException:
            failure = "timeout"
        except httpx.RequestError:
            failure = "connection"
        if failure == "timeout":
            raise HpsiMcpTimeoutError("Request timed out.")
        if failure == "connection":
            raise HpsiMcpConnectionError("Request failed before a response was received.")
        return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        message = self._error_message(response)

        # Checked before the 401/402 circuit breaker below, and that ordering is
        # the whole fix. An empty Credit balance is not an authentication
        # problem: the API key is valid, the account is real, and topping up
        # resolves it. Tripping the breaker would raise `HpsiMcpConfigError` and
        # permanently disable this client object, so every later call — including
        # the ones made after Credits are added — would fail without ever
        # reaching the network.
        if response.status_code in {402, 403} and self._is_insufficient_credits(response):
            body = self._response_body(response)
            raise HpsiMcpInsufficientCreditsError(
                message,
                status_code=response.status_code,
                response_text=response.text,
                body=body,
                credits_required=body.get("credits_required"),
                credits_remaining=body.get("credits_remaining"),
                upgrade_url=body.get("upgrade_url"),
                register_url=body.get("register"),
            )

        if response.status_code in {401, 402}:
            self._trip_auth_circuit(response)
        if response.status_code == 403:
            body = self._response_body(response)
            conv = self._conversion_fields(body)
            raise HpsiMcpAuthError(
                message,
                status_code=response.status_code,
                response_text=response.text,
                body=body,
                register_url=conv["register_url"],
                pricing_url=conv["pricing_url"],
                upgrade_message=conv["upgrade_message"],
            )
        if response.status_code == 402:
            error = self._payment_error(message, response)
            if self._api_key is None:
                self._warn_anon_payment_required(error.price, response)
            raise error
        if response.status_code == 429:
            if self._api_key is None:
                self._warn_anon_rate_limited(response)
            body = self._response_body(response)
            conv = self._conversion_fields(body)
            tool = body.get("tool")
            limit = body.get("limit")
            window = body.get("window")
            reset_at = body.get("reset_at")
            raise HpsiMcpRateLimitError(
                message,
                status_code=response.status_code,
                response_text=response.text,
                body=body,
                tool=tool if isinstance(tool, str) else None,
                limit=limit if isinstance(limit, int) and not isinstance(limit, bool) else None,
                window=window if isinstance(window, str) else None,
                retry_after_seconds=self._retry_after_seconds(response, body),
                reset_at=reset_at if isinstance(reset_at, str) else None,
                register_url=conv["register_url"],
                pricing_url=conv["pricing_url"],
                upgrade_message=conv["upgrade_message"],
                register=body.get("register") if isinstance(body.get("register"), str) else None,
                upgrade_hint=body.get("upgrade_hint") if isinstance(body.get("upgrade_hint"), str) else None,
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
        body = None
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
            # Reaching a 402 with no wallet configured means this client has a
            # real api_key (construction requires one or the other — see
            # HpsiMcpClient.__init__): an already-registered account whose
            # quota this Pro tool / overage call exceeds, not an unidentified
            # caller. There is nothing to "register" — the one lever left is
            # paying per call.
            if price:
                message = (
                    f"{message} Pay {price} per call by configuring "
                    "HpsiMcpClient(wallet=X402Wallet(...)), or upgrade your plan "
                    "at https://hpsilab.com/pricing."
                )
            else:
                message = (
                    f"{message} Configure HpsiMcpClient(wallet=X402Wallet(...)) "
                    "to pay per call, or upgrade your plan at "
                    "https://hpsilab.com/pricing."
                )
        return HpsiMcpPaymentError(
            message,
            status_code=response.status_code,
            response_text=response.text,
            body=body if isinstance(body, dict) else None,
            accepts=accepts,
            tool=tool,
            price=price,
        )

    def _decode_json(self, response: httpx.Response) -> Any:
        decode_failed = False
        try:
            result = response.json()
        except ValueError:
            decode_failed = True
        if decode_failed:
            raise HpsiMcpResponseError(
                "API response was not valid JSON.",
                status_code=response.status_code,
                response_text=response.text,
            )
        return result

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

    def _is_insufficient_credits(self, response: httpx.Response) -> bool:
        """Whether this response is the "out of Credits" refusal.

        Read off the body rather than the status because the status is shared:
        402 is also the x402 payment challenge, and 403 also means "your plan
        does not include this tool". A challenge is excluded explicitly — it
        carries a non-empty ``accepts``, which is the offer a wallet settles, and
        if a body ever arrived with both markers, treating it as payable (an
        action the caller can complete) beats treating it as a dead end.

        Mirrors backend ``app.core.error_contract.is_insufficient_credits`` and
        ``mcp_server/errors.py::_is_insufficient_credits``; all three must agree,
        because they are the same decision made at three hops of one call.
        """
        body = self._response_body(response)
        accepts = body.get("accepts")
        if isinstance(accepts, list) and accepts:
            return False
        return body.get("error") == "insufficient_credits"

    @staticmethod
    def _retry_after_seconds(response: httpx.Response, body: dict) -> Optional[int]:
        """How long to wait, header first.

        ``Retry-After`` wins over the body's ``retry_after_seconds`` because a
        proxy or gateway may rewrite the header to reflect its own queueing, and
        that is the number that actually governs when this request will be let
        through. Both are accepted so a bounded retry still has something to work
        with when only one is present.
        """
        raw = response.headers.get("retry-after")
        if raw:
            try:
                return max(0, int(float(raw)))
            except (TypeError, ValueError):
                pass
        value = body.get("retry_after_seconds")
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
        return None

    def _response_body(self, response: httpx.Response) -> dict:
        """Parsed JSON body, or `{}` for anything that isn't a JSON object —
        never raises. Feeds `HpsiMcpAuthError.body`/`HpsiMcpRateLimitError.body`
        so the complete backend response survives on the raised exception even
        for fields not promoted to a named attribute."""
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def _conversion_fields(self, body: dict) -> dict:
        """Extract register_url/pricing_url/upgrade_message from either shape
        the backend may send: the nested `upgrade.{register_url,pricing_url,
        message}` (preferred when present), or the flat `register`/
        `upgrade_hint` fallback. Mirrors
        mcp_server/errors.py::_conversion_from_response so the two stay in
        sync (docs/error-contract.md section 1.3)."""
        upgrade = body.get("upgrade")
        upgrade = upgrade if isinstance(upgrade, dict) else {}

        register_url = upgrade.get("register_url")
        if not (isinstance(register_url, str) and register_url):
            register_url = body.get("register")

        pricing_url = upgrade.get("pricing_url")

        upgrade_message = upgrade.get("message")
        if not (isinstance(upgrade_message, str) and upgrade_message):
            upgrade_message = body.get("upgrade_hint")

        return {
            "register_url": register_url if isinstance(register_url, str) and register_url else None,
            "pricing_url": pricing_url if isinstance(pricing_url, str) and pricing_url else None,
            "upgrade_message": upgrade_message if isinstance(upgrade_message, str) and upgrade_message else None,
        }

    def _register_url_from_response(self, response: httpx.Response) -> str:
        """Read the register URL the backend attached to this response, or
        fall back to the hardcoded default. Checks the original nested
        `upgrade.register_url` first (see
        backend/app/middleware/rate_limit.py::_UPGRADE_NUDGE), then the newer
        flat `register` string (see
        backend/app/middleware/rate_limit.py::_CONVERSION_LINKS) — a backend
        deploy carrying only the flat field must still reach this warning
        without an SDK release."""
        register_url = "https://hpsilab.com/register"
        try:
            body = response.json()
        except ValueError:
            return register_url
        if not isinstance(body, dict):
            return register_url

        upgrade = body.get("upgrade")
        candidate = upgrade.get("register_url") if isinstance(upgrade, dict) else None
        if not (isinstance(candidate, str) and candidate):
            candidate = body.get("register")
        if isinstance(candidate, str) and candidate:
            register_url = candidate
        return (
            safe_public_url(register_url, fallback="https://hpsilab.com/register")
            or "https://hpsilab.com/register"
        )

    def _warn_anon_payment_required(self, price: Optional[str], response: httpx.Response) -> None:
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
        register_url = self._register_url_from_response(response)
        warnings.warn(
            f"hpsilab: Free API key required. Register at {register_url}, "
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

        Same unified copy as `_warn_anon_payment_required` — see
        backend/app/middleware/rate_limit.py::_SIMPLE_QUOTA_MESSAGE. Only the
        register URL is still read from the response body, since that value
        can move server-side without a new SDK release.
        """
        register_url = self._register_url_from_response(response)
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


def register(
    email: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 30.0,
    transport: Optional[httpx.BaseTransport] = None,
) -> dict:
    """Register a free account and get back an API key — no client instance
    needed.

    `HpsiMcpClient()` now requires an identity (api_key or wallet) to even
    construct, per the mandatory-API-key change — this is the one entry
    point that works before you have either. Wraps the same
    `POST /api/agent/register` `HpsiMcpClient.register_account` uses. For
    agents: no password, no wallet, no web form; the account is bound to this
    caller server-side (see `HpsiMcpClient.register_account`'s docstring for
    the idempotency/binding details).

    `transport=` mirrors `HpsiMcpClient`'s constructor param — pass an
    `httpx.MockTransport` in tests instead of hitting a real network.

    Typical use::

        result = hpsilab_mcp.register(email="you@example.com")
        client = HpsiMcpClient(api_key=result["api_key"])
    """
    headers = build_tracking_headers(
        source=_TRACKING_SOURCE,
        client=_TRACKING_CLIENT,
        version=__version__,
        tool="register_account",
    )
    headers["User-Agent"] = _USER_AGENT
    failure: Optional[str] = None
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), transport=transport, timeout=timeout) as http:
            response = http.post("/api/agent/register", json={"email": email}, headers=headers)
    except httpx.TimeoutException:
        failure = "timeout"
    except httpx.RequestError:
        failure = "connection"
    if failure == "timeout":
        raise HpsiMcpTimeoutError("Request timed out.")
    if failure == "connection":
        raise HpsiMcpConnectionError("Request failed before a response was received.")

    if response.status_code >= 400:
        try:
            detail = response.json()
            message = detail.get("detail") or detail.get("message") or response.text
        except ValueError:
            message = response.text
        raise HpsiMcpAPIError(
            f"Registration failed ({response.status_code}): {message}",
            status_code=response.status_code,
            response_text=response.text,
        )

    decode_failed = False
    try:
        result = response.json()
    except ValueError:
        decode_failed = True
    if decode_failed:
        raise HpsiMcpResponseError(
            "Registration response was not valid JSON.",
            response_text=response.text,
        )
    return result
