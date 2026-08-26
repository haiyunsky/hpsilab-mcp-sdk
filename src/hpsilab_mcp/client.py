"""Synchronous REST client for H|ψ⟩ Quantum Finance APIs."""

from __future__ import annotations

import time
import uuid
import warnings
from decimal import Decimal, InvalidOperation
from threading import RLock
from types import TracebackType
from typing import Any, Callable, Mapping, Optional, Sequence, Type
from urllib.parse import quote

import httpx
from email_validator import EmailNotValidError, validate_email

from . import __version__
from .errors import (
    HpsiMcpAPIError,
    HpsiMcpAuthError,
    HpsiMcpConfigError,
    HpsiMcpConnectionError,
    HpsiMcpInsufficientCreditsError,
    HpsiMcpPaymentError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
    HpsiMcpSettlementUnknownError,
    HpsiMcpTimeoutError,
    HpsiMcpValidationError,
    redact_sensitive_text,
    safe_public_url,
)
from .payments import X402Wallet, wallet_from_env
from .mcp_result import full_tool_result
from .policy import (
    CREDITS_ONLY,
    X402_FALLBACK,
    PaymentBudget,
    PaymentPolicy,
    normalize_network,
    resolve_asset,
)
from .policy import (
    decide as decide_payment,
)
from .tracking import build_tracking_headers

DEFAULT_BASE_URL = "https://hpsilab.com"
DEFAULT_INSUFFICIENT_CREDITS_TTL_SECONDS = 60.0

_TRACKING_SOURCE = "sdk"
_TRACKING_CLIENT = "python-sdk"
_USER_AGENT = f"hpsilab-python-sdk/{__version__}"
_ANON_KEY_PREFIX = "hpsi_anon_"
_ANON_KEY_HEADER = "X-HPSILAB-Anon-Key"

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


def _registration_email(value: object) -> str:
    """Validate and normalize registration email before any network I/O."""
    if value is None or not isinstance(value, str) or not value.strip():
        raise HpsiMcpValidationError(
            "A valid email address is required to create an account.",
            error="email_required",
        )
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise HpsiMcpValidationError(
            "Enter a valid email address.", error="invalid_email"
        ) from exc


def _default_payment_mode(
    *, wallet_was_passed: bool, wallet_from_environment: bool, has_api_key: bool
) -> str:
    """Whether an unstated `payment_mode` means "may pay".

    The engineering spec requires an *explicit* opt-in before this SDK spends
    money, and the whole question is what counts as explicit. Writing
    `HpsiMcpClient(wallet=X402Wallet(...))` in source does: a wallet is not
    something that appears in a constructor by accident.

    `HPSILAB_X402_PRIVATE_KEY` in the environment does not. It is ambient, it
    is frequently left over from another project, and a keyed client that finds
    one should go on paying with Credits rather than quietly start paying with
    crypto — which is what this SDK used to do.

    The one exception is a client with *no* API key: there the environment
    wallet is the only credential it has, so it is unambiguously the credential
    it was meant to use. Refusing to pay in that case leaves a client that
    cannot complete a single call.
    """
    if wallet_was_passed:
        return X402_FALLBACK
    if wallet_from_environment and not has_api_key:
        return X402_FALLBACK
    return CREDITS_ONLY


def _offer_mismatch(approved, agreed: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Why the signed payment disagrees with the approved offer, or None.

    `agreed is None` means the wallet could not say what it signed. That is not
    a mismatch and is deliberately not treated as one — refusing every wallet
    that predates `sign()` would break paying clients to close a gap none of
    them have been shown to have. It is also not silently fine: the caller
    simply has no check available, which the comment at the call site says.

    Compared on amount, asset and network rather than by identity, because the
    two objects come from different parsers of the same JSON and will not be
    the same dict.
    """
    if agreed is None:
        return None
    raw_amount = agreed.get("maxAmountRequired", agreed.get("amount"))
    try:
        signed_units = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError, ValueError):
        return "the signed payment carries no readable amount"
    # `approved.amount` is in whole USDC; the wire value is base units.
    if signed_units != approved.amount * (Decimal(10) ** 6):
        return f"signed {signed_units} base units, approved {approved.amount} USDC"
    signed_network = normalize_network(agreed.get("network"))
    if signed_network != approved.network:
        return f"signed on {signed_network}, approved {approved.network}"
    signed_asset = resolve_asset(agreed.get("asset"))
    if not signed_asset or signed_asset[0] != approved.asset_symbol:
        return f"signed a different asset than the approved {approved.asset_symbol}"
    return None


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
        payment_mode: Optional[str] = None,
        payment_policy: Optional[PaymentPolicy] = None,
        insufficient_credits_ttl_seconds: float = DEFAULT_INSUFFICIENT_CREDITS_TTL_SECONDS,
        anonymous_credential: Optional[str] = None,
        mcp_transport: Optional[Callable[[str, Mapping[str, Any]], Any]] = None,
    ) -> None:
        if (
            isinstance(insufficient_credits_ttl_seconds, bool)
            or not isinstance(insufficient_credits_ttl_seconds, (int, float))
            or insufficient_credits_ttl_seconds < 0
        ):
            raise ValueError(
                "insufficient_credits_ttl_seconds must be a non-negative number"
            )
        # Pay-per-call is opt-in: an explicit wallet, or HPSILAB_X402_PRIVATE_KEY
        # in the environment. Holding the wallet is not the same as consenting
        # to spend it — `payment_policy` decides that, and defaults to
        # `credits_only`. See `_default_payment_mode`.
        resolved_wallet = wallet if wallet is not None else wallet_from_env()

        if anonymous_credential is not None and not anonymous_credential.startswith(
            _ANON_KEY_PREFIX
        ):
            raise HpsiMcpConfigError("Invalid anonymous credential format.")

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
        elif anonymous_credential:
            request_headers["Authorization"] = f"Bearer {anonymous_credential}"

        self._api_key = api_key
        self._anonymous_credential = anonymous_credential
        self._mcp_transport = mcp_transport
        self._wallet = resolved_wallet
        self._payment_policy = self._initial_payment_policy(
            payment_policy,
            payment_mode,
            wallet_was_passed=wallet is not None,
            wallet_from_environment=wallet is None and resolved_wallet is not None,
            has_api_key=bool(api_key),
        )
        # A wallet-only SDK caller is not an anonymous web visitor. Without an
        # explicit transport signal the REST middleware sees "no Authorization"
        # and may grant browser trial access, so the wallet is never challenged.
        # This header grants no access; it only selects per-call x402. Keyed
        # clients omit it so their normal route remains Credits first.
        if not api_key and resolved_wallet is not None:
            request_headers["X-HPSILAB-Payment-Mode"] = (
                "x402" if self._payment_policy.pays else "credits_only"
            )
        elif not api_key and not anonymous_credential:
            request_headers["X-HPSILAB-Payment-Mode"] = "anonymous"
        self._budget = PaymentBudget()
        # Separate from the authentication breaker below, and that separation is
        # the point: a wallet that cannot sign says nothing about an API key
        # that works. Tripping this one stops the client paying and leaves every
        # Credits-funded call working.
        self._x402_disabled_reason: Optional[str] = None
        # call_id -> tool, for every call whose payment outcome is unknown.
        # These are the calls a reconciliation run has to resolve; the client
        # keeps them rather than the caller having to scrape them out of
        # exception text.
        self._unresolved_settlements: dict[str, str] = {}
        self._auth_failed = False
        self._auth_failure_message: Optional[str] = None
        self._insufficient_credits_ttl_seconds = float(insufficient_credits_ttl_seconds)
        self._insufficient_credits_failure: Optional[tuple[float, dict[str, Any]]] = (
            None
        )
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

    def call_tool(
        self,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        include_metadata: bool = False,
        **tool_arguments: Any,
    ) -> Any:
        """Call an MCP tool through the optional transport adapter.

        The default return is the adapter's original value. Set
        ``include_metadata=True`` to get an :class:`McpToolResult` whose
        metadata is read directly from MCP ``CallToolResult._meta``.
        """
        if not name:
            raise ValueError("Tool name is required.")
        if self._mcp_transport is None:
            raise HpsiMcpConfigError(
                "call_tool requires an mcp_transport adapter. REST methods remain available without one."
            )
        merged = dict(arguments or {})
        duplicate = merged.keys() & tool_arguments.keys()
        if duplicate:
            names = ", ".join(sorted(duplicate))
            raise ValueError(f"Duplicate MCP tool arguments: {names}")
        merged.update(tool_arguments)
        raw_result = self._mcp_transport(name, merged)
        return full_tool_result(raw_result) if include_metadata else raw_result

    def __repr__(self) -> str:  # pragma: no cover - diagnostic safety
        api_key_state = "configured" if self._api_key else "not-configured"
        wallet_state = "configured" if self._wallet is not None else "not-configured"
        return f"<HpsiMcpClient api_key={api_key_state} wallet={wallet_state}>"

    def set_api_key(self, api_key: Optional[str]) -> None:
        """Replace the API key and reset this client's authentication breaker."""
        with self._request_lock:
            self._api_key = api_key
            if api_key:
                self._client.headers["Authorization"] = f"Bearer {api_key}"
                self._client.headers.pop("X-HPSILAB-Payment-Mode", None)
            else:
                if self._anonymous_credential:
                    self._client.headers["Authorization"] = (
                        f"Bearer {self._anonymous_credential}"
                    )
                else:
                    self._client.headers.pop("Authorization", None)
                if self._wallet is not None:
                    self._client.headers["X-HPSILAB-Payment-Mode"] = (
                        "x402" if self._payment_policy.pays else "credits_only"
                    )
                elif not self._anonymous_credential:
                    self._client.headers["X-HPSILAB-Payment-Mode"] = "anonymous"
            self._reset_auth_circuit()
            self._insufficient_credits_failure = None

    @property
    def anonymous_credential(self) -> Optional[str]:
        return self._anonymous_credential

    def set_anonymous_credential(self, credential: Optional[str]) -> None:
        """Restore or clear the SDK-channel anonymous Billing Owner."""
        if credential is not None and not credential.startswith(_ANON_KEY_PREFIX):
            raise HpsiMcpConfigError("Invalid anonymous credential format.")
        with self._request_lock:
            self._anonymous_credential = credential
            if self._api_key:
                return
            if credential:
                self._client.headers["Authorization"] = f"Bearer {credential}"
                self._client.headers.pop("X-HPSILAB-Payment-Mode", None)
            else:
                self._client.headers.pop("Authorization", None)
                self._client.headers["X-HPSILAB-Payment-Mode"] = (
                    "x402" if self._wallet is not None and self._payment_policy.pays else
                    "credits_only" if self._wallet is not None else "anonymous"
                )

    def clear_insufficient_credits_circuit(self) -> None:
        """Allow an immediate balance recheck after Credits are added."""
        with self._request_lock:
            self._insufficient_credits_failure = None

    def set_wallet(self, wallet: Optional[X402Wallet]) -> None:
        """Replace the x402 wallet and reset this client's breakers.

        The payment policy is deliberately *not* changed. Swapping a wallet is
        a repair — the old one was empty, or its key rotated — and repairing it
        must not silently promote a `credits_only` client into one that spends.

        This is also how a client latched shut by an unresolved settlement is
        reopened, once reconciliation has said what happened to it. The record
        of *which* calls were unresolved is deliberately not cleared: it is the
        evidence, and a caller resuming payments still needs it.
        """
        with self._request_lock:
            if wallet is None and not self._api_key:
                raise HpsiMcpConfigError(_REMOVE_AUTH_MESSAGE)
            self._wallet = wallet
            if not self._api_key:
                if wallet is None:
                    self._client.headers.pop("X-HPSILAB-Payment-Mode", None)
                else:
                    self._client.headers["X-HPSILAB-Payment-Mode"] = (
                        "x402" if self._payment_policy.pays else "credits_only"
                    )
            self._reset_auth_circuit()
            self._x402_disabled_reason = None

    @staticmethod
    def _initial_payment_policy(
        payment_policy: Optional[PaymentPolicy],
        payment_mode: Optional[str],
        *,
        wallet_was_passed: bool,
        wallet_from_environment: bool,
        has_api_key: bool,
    ) -> PaymentPolicy:
        """Reconcile the two ways a caller can state payment intent.

        `payment_policy=` is the full surface; `payment_mode=` is the shorthand
        for the one field most callers touch. Given both, the explicit mode
        wins — it is the more specific statement, and a policy object is often
        a shared default that a single call site wants to override.
        """
        policy = payment_policy or PaymentPolicy()
        if payment_mode is not None:
            return policy.with_mode(payment_mode)
        if payment_policy is not None:
            # The caller built a policy; its mode is a decision, not a default.
            return policy
        return policy.with_mode(
            _default_payment_mode(
                wallet_was_passed=wallet_was_passed,
                wallet_from_environment=wallet_from_environment,
                has_api_key=has_api_key,
            )
        )

    @property
    def payment_policy(self) -> PaymentPolicy:
        """The spending rules in force. Frozen — use `set_payment_policy`."""
        return self._payment_policy

    def set_payment_policy(
        self,
        policy: Optional[PaymentPolicy] = None,
        *,
        mode: Optional[str] = None,
    ) -> None:
        """Replace the spending rules. Budgets already spent are not reset.

        Deliberately: a caller that has spent $4 of a $5 session ceiling must
        not be able to reach $9 by re-stating the same ceiling. Build a new
        client for a genuinely new session.
        """
        with self._request_lock:
            new_policy = policy if policy is not None else self._payment_policy
            if mode is not None:
                new_policy = new_policy.with_mode(mode)
            self._payment_policy = new_policy
            if not self._api_key and self._wallet is not None:
                self._client.headers["X-HPSILAB-Payment-Mode"] = (
                    "x402" if new_policy.pays else "credits_only"
                )

    def payment_spend_summary(self) -> dict:
        """What has been spent and what remains — for an agent to reason about.

        A caller deciding whether to attempt an expensive call should be able to
        ask, rather than discover the answer by being refused.
        """
        with self._request_lock:
            summary = self._budget.summary(self._payment_policy)
            summary["x402_disabled_reason"] = self._x402_disabled_reason
            # Money that may have moved without a confirmed answer. Reported
            # separately from `session_spent_usd` (which already counts it) so a
            # caller can tell "spent" from "spent, outcome unconfirmed".
            summary["unresolved_settlements"] = dict(self._unresolved_settlements)
            return summary

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
        return self._get(
            f"/api/ai_prediction/{self._path_symbol(symbol)}",
            tool_name="get_ai_prediction",
        )

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
        return self._get(
            f"/api/option_pressure/{self._path_symbol(symbol)}",
            tool_name="get_option_pressure",
        )

    def get_pretrade_risk_scan(self, symbol: str) -> Any:
        return self._get(
            "/api/pretrade-risk-scan",
            params={"symbol": self._clean_symbol(symbol)},
            tool_name="get_pretrade_risk_scan",
        )

    def get_equity_curve(self, symbol: str) -> Any:
        return self._get(
            f"/api/equity_curve/{self._path_symbol(symbol)}",
            tool_name="get_equity_curve",
        )

    def get_equity_curves(self, symbol: str) -> Any:
        """Deprecated plural alias of `get_equity_curve`, kept for one release."""
        warnings.warn(
            "get_equity_curves() is deprecated; use get_equity_curve().",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_equity_curve(symbol)

    def get_monte_carlo(self, symbol: str) -> Any:
        return self._get(
            f"/api/monte_carlo/{self._path_symbol(symbol)}", tool_name="get_monte_carlo"
        )

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
        email = _registration_email(email)
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

    def _tool_headers(
        self, tool_name: Optional[str], call_id: Optional[str] = None
    ) -> Optional[dict]:
        """Per-request override merged on top of the client's default headers
        (see `build_tracking_headers`) — only `X-HPSILAB-Tool` and
        `X-Request-Id` vary per call, the rest (source/client/version/
        User-Agent/Authorization/...) stay put."""
        if not tool_name and not call_id:
            return None
        headers = (
            build_tracking_headers(
                source=_TRACKING_SOURCE,
                client=_TRACKING_CLIENT,
                version=__version__,
                tool=tool_name,
            )
            if tool_name
            else {}
        )
        if call_id:
            # The API threads one id through quote → pay → settle and enforces
            # uniqueness on it (a settlement is unique per *logical call*, which
            # `transaction_hash` cannot express: one call settled twice would be
            # two different transactions). Without this header the API mints a
            # fresh id per HTTP request, and a caller that retried a paid call
            # would defeat the constraint built to stop exactly that.
            #
            # Set here rather than as a client default so it overrides any
            # `headers={"X-Request-Id": ...}` the caller pinned at construction
            # — a single id shared by every call would make the second paid call
            # collide with the first.
            headers["X-Request-Id"] = call_id
        return headers

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
            self._ensure_insufficient_credits_circuit_closed()
            # One id for the whole logical call — the unpaid attempt and the
            # paid retry below are the same call, and the API's settlement
            # ledger is unique on it (spec §12.1/§12.2).
            call_id = f"call_{uuid.uuid4().hex}"
            response = self._send(method, path, params, tool_name, call_id=call_id)

            # A 402 is retryable exactly once, and only after a configured
            # wallet successfully produces payment headers.
            #
            # The condition is deliberately "there is something settleable
            # here", not "the status was 402". Two different things arrive on
            # 402 and only one of them can be paid:
            #
            # * out of Credits — no `accepts`, so a wallet has nothing to sign;
            #   handing it one means `payment_headers` raises and an empty
            #   balance is reported as a permanently broken client;
            # * a malformed offer (`x402Version` and no options) — equally
            #   unsignable, and equally not the caller's fault.
            #
            # Requiring a non-empty `accepts` covers both without enumerating
            # them, and is the same discriminator the backend, the MCP server
            # and the frontend apply (see `contracts/error_contract_fixtures.json`).
            refusal: Optional[str] = None
            if response.status_code == 402 and self._has_settleable_offer(response):
                decision = decide_payment(
                    self._response_body(response),
                    tool_name=tool_name,
                    policy=self._payment_policy,
                    budget=self._budget,
                    has_wallet=self._wallet is not None,
                    x402_disabled_reason=self._x402_disabled_reason,
                )
                if not decision.pay:
                    refusal = decision.reason
                else:
                    response = self._settle_once(
                        method,
                        path,
                        params,
                        tool_name,
                        response,
                        decision.offer,
                        call_id,
                    )

            self._raise_for_status(response, payment_refusal=refusal)
            return self._decode_json(response)

    def _settle_once(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, str]],
        tool_name: Optional[str],
        challenge: httpx.Response,
        offer,
        call_id: Optional[str] = None,
    ) -> httpx.Response:
        """Sign one offer, charge the budget, retry once. Never twice.

        The budget is charged once the authorization is signed and about to be
        sent, and is not credited back if the retry then fails. The two edges
        are deliberate: before signing nothing can have moved, so charging
        would be wrong; after the request leaves we no longer know whether it
        settled, and the spec's "uncertain prior payment: resolve state before
        another payment attempt" has exactly one safe local resolution — assume
        it moved.
        """
        try:
            signer = getattr(self._wallet, "sign", None)
            if signer is not None:
                payment_headers, agreed = signer(challenge)
            else:
                # A wallet predating `sign()`. It can still pay; what it cannot
                # do is tell us what it agreed to, so the check below is skipped
                # rather than silently passed.
                payment_headers, agreed = self._wallet.payment_headers(challenge), None
        except Exception:
            # Do not chain third-party wallet exceptions: a wallet
            # implementation may include signed payment context in its
            # exception text or attributes, which must not leak into user
            # tracebacks or logs.
            self._disable_x402(
                "the configured wallet could not sign the payment challenge"
            )
            return challenge
        if not payment_headers:
            self._disable_x402("the configured wallet produced no payment headers")
            return challenge

        # The policy chose one offer from `accepts`; the wallet chose one from
        # the same list, independently, and the signature commits to the
        # wallet's. Nothing made those the same choice. A challenge listing
        # several offers could be approved at one price and signed at another —
        # and the budget would then be charged for the wrong one, which is the
        # quiet version of the failure rather than the loud one.
        mismatch = _offer_mismatch(offer, agreed)
        if mismatch:
            self._disable_x402(
                "the wallet signed a different offer than the policy approved"
            )
            return challenge

        self._budget.charge(offer.amount)
        try:
            response = self._send(
                method, path, params, tool_name, extra=payment_headers, call_id=call_id
            )
        except (HpsiMcpTimeoutError, HpsiMcpConnectionError):
            # The authorization went out and no answer came back. Whether it
            # settled is unknowable from here, so stop paying rather than let
            # a retry sign a second one for the same logical call.
            self._record_unresolved_settlement(call_id, tool_name)
            self._disable_x402(
                "a payment was sent but its outcome is unknown (the request did not complete)"
            )
            raise

        # Paid, and still refused. Repeating cannot help and another attempt
        # would just sign again, so close the x402 path — otherwise a server
        # stuck on 402 drains the wallet one call at a time. Credits-funded
        # calls are untouched; the API key is not what failed here.
        if response.status_code == 402 and not self._is_insufficient_credits(response):
            self._disable_x402(
                "a payment was accepted by the wallet but the server still refused"
            )
        return response

    def _record_unresolved_settlement(
        self, call_id: Optional[str], tool_name: Optional[str]
    ) -> None:
        """Remember a call whose payment outcome is not known.

        Kept so `payment_spend_summary()` can hand the ids to whoever runs
        reconciliation. Without them the caller knows money may have moved and
        not for which calls, which is the state that cannot be reconciled.
        """
        self._unresolved_settlements[call_id or "(unassigned)"] = tool_name or ""

    def _disable_x402(self, reason: str) -> None:
        """Close the x402 path for this client, leaving the rest of it working.

        Never carries wallet-supplied text: the reasons are this module's own
        fixed strings, so a signature or key cannot reach a log through here.
        """
        self._x402_disabled_reason = reason

    def _reset_auth_circuit(self) -> None:
        self._auth_failed = False
        self._auth_failure_message = None

    def _ensure_auth_circuit_closed(self) -> None:
        if self._auth_failed:
            raise HpsiMcpConfigError(
                self._auth_failure_message or _MISSING_AUTH_MESSAGE
            )

    def _remember_insufficient_credits(
        self, error: HpsiMcpInsufficientCreditsError
    ) -> None:
        if self._insufficient_credits_ttl_seconds <= 0:
            return
        self._insufficient_credits_failure = (
            time.monotonic() + self._insufficient_credits_ttl_seconds,
            {
                "message": str(error),
                "status_code": error.status_code,
                "response_text": error.response_text,
                "body": error.body,
                "credits_required": error.credits_required,
                "credits_remaining": error.credits_remaining,
                "upgrade_url": error.upgrade_url,
                "register_url": error.register_url,
            },
        )

    def _ensure_insufficient_credits_circuit_closed(self) -> None:
        failure = self._insufficient_credits_failure
        if failure is None:
            return
        expires_at, fields = failure
        now = time.monotonic()
        if now >= expires_at:
            self._insufficient_credits_failure = None
            return
        error = HpsiMcpInsufficientCreditsError(**fields)
        error.circuit_open = True
        error.retry_after_seconds = max(1, int(expires_at - now + 0.999))
        raise error

    @staticmethod
    def _has_settleable_offer(response: httpx.Response) -> bool:
        """True when the body carries payment options a wallet could sign.

        `accepts` being a non-empty list *is* the offer. A body without it —
        whatever else it says — leaves nothing to settle, so attempting payment
        against it can only fail.
        """
        try:
            body = response.json()
        except ValueError:
            return False
        if not isinstance(body, dict):
            return False
        accepts = body.get("accepts")
        return isinstance(accepts, list) and bool(accepts)

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
        call_id: Optional[str] = None,
    ) -> httpx.Response:
        headers = self._tool_headers(tool_name, call_id) or {}
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
            raise HpsiMcpConnectionError(
                "Request failed before a response was received."
            )
        issued = response.headers.get(_ANON_KEY_HEADER)
        if (
            issued
            and issued.startswith(_ANON_KEY_PREFIX)
            and not self._api_key
        ):
            self._anonymous_credential = issued
            self._client.headers["Authorization"] = f"Bearer {issued}"
            self._client.headers.pop("X-HPSILAB-Payment-Mode", None)
        return response

    def _raise_for_status(
        self, response: httpx.Response, payment_refusal: Optional[str] = None
    ) -> None:
        if response.status_code < 400:
            return

        message = self._error_message(response)

        # First, ahead of everything: a settlement the API cannot resolve.
        #
        # Nothing below may claim this response. Every other branch here ends in
        # advice that is safe to act on — wait, top up, reconfigure, pay. This
        # one has no safe action at all, and the two branches it most resembles
        # (a 402 offer, a generic 5xx) both read as "try again", which is the
        # one thing that turns an unresolved payment into two payments.
        unresolved = self._settlement_unknown(message, response)
        if unresolved is not None:
            self._record_unresolved_settlement(unresolved.call_id, unresolved.tool)
            self._disable_x402(
                "a payment was sent and the API could not confirm whether it settled"
            )
            raise unresolved

        # Checked before the 401/402 circuit breaker below, and that ordering is
        # the whole fix. An empty Credit balance is not an authentication
        # problem: the API key is valid, the account is real, and topping up
        # resolves it. Tripping the breaker would raise `HpsiMcpConfigError` and
        # permanently disable this client object, so every later call — including
        # the ones made after Credits are added — would fail without ever
        # reaching the network.
        if response.status_code in {402, 403} and self._is_insufficient_credits(
            response
        ):
            body = self._response_body(response)
            error = HpsiMcpInsufficientCreditsError(
                message,
                status_code=response.status_code,
                response_text=response.text,
                body=body,
                credits_required=body.get("credits_required"),
                credits_remaining=body.get("credits_remaining"),
                upgrade_url=body.get("upgrade_url"),
                register_url=body.get("register"),
            )
            self._remember_insufficient_credits(error)
            raise error

        # A 402 that is not a Credits refusal is a payment offer, and it is
        # raised as one *before* the circuit breaker below can see it.
        #
        # The ordering used to be the other way round, which made
        # `_payment_error` unreachable for status 402: `_trip_auth_circuit`
        # raises unconditionally, so every x402 challenge came out as
        # `HpsiMcpConfigError` — "this client is misconfigured, build a new
        # one" — and the challenge, including `accepts`, was thrown away. A
        # caller without a wallet could not see what they were being asked to
        # pay, and a caller who then attached one had a client that was already
        # latched shut.
        #
        # A payment-required response is not a bad credential. The key is
        # valid, the account is real, and the remedy is money rather than
        # reconfiguration — the same reasoning that already moved the Credits
        # refusal ahead of the breaker.
        if response.status_code == 402:
            error = self._payment_error(message, response, payment_refusal)
            if self._api_key is None:
                self._warn_anon_payment_required(error.price, response)
            raise error
        if response.status_code == 401:
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
                limit=limit
                if isinstance(limit, int) and not isinstance(limit, bool)
                else None,
                window=window if isinstance(window, str) else None,
                retry_after_seconds=self._retry_after_seconds(response, body),
                reset_at=reset_at if isinstance(reset_at, str) else None,
                upgrade_available=body.get("upgrade_available")
                if isinstance(body.get("upgrade_available"), bool)
                else None,
                upgrade_url=body.get("upgrade_url")
                if isinstance(body.get("upgrade_url"), str)
                else None,
                register_url=conv["register_url"] if self._api_key is None else None,
                pricing_url=conv["pricing_url"] if self._api_key is not None else None,
                upgrade_message=body.get("upgrade_message")
                if isinstance(body.get("upgrade_message"), str)
                else conv["upgrade_message"],
                register=(
                    body.get("register")
                    if self._api_key is None and isinstance(body.get("register"), str)
                    else None
                ),
                upgrade_hint=body.get("upgrade_hint")
                if isinstance(body.get("upgrade_hint"), str)
                else None,
            )
        raise HpsiMcpAPIError(
            message,
            status_code=response.status_code,
            response_text=response.text,
        )

    def _settlement_unknown(
        self, message: str, response: httpx.Response
    ) -> Optional[HpsiMcpSettlementUnknownError]:
        """The response saying a payment may have gone through, or None.

        Keyed on the body's `settlement_status`, not on the status code. The
        code is the API's way of saying "this call did not produce an answer"
        and could reasonably change or differ per transport; the field is the
        API's way of saying *why*, and it is the part that must not be guessed
        at. A body that does not say `unknown` is not one of these — an
        unresolved settlement is too expensive to infer.
        """
        body = self._response_body(response)
        if body.get("settlement_status") != "unknown":
            return None
        call_id = body.get("call_id")
        tool = body.get("tool")
        return HpsiMcpSettlementUnknownError(
            message,
            call_id=call_id if isinstance(call_id, str) else None,
            tool=tool if isinstance(tool, str) else None,
            settlement_status="unknown",
            status_code=response.status_code,
            response_text=response.text,
            body=body,
        )

    def _payment_error(
        self,
        message: str,
        response: httpx.Response,
        payment_refusal: Optional[str] = None,
    ) -> HpsiMcpPaymentError:
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

        if self._wallet is not None and payment_refusal:
            # A wallet is present, an offer arrived, and this client declined
            # it. Saying why is the only thing that separates "the server
            # offered nothing payable" from "your own policy said no" — two
            # failures with different fixes, and only one of them is the
            # server's doing. Checked after `self._wallet`, because a caller
            # with no wallet is better served by the hint below than by being
            # told their policy is `credits_only`.
            message = f"{message} No payment was attempted: {payment_refusal}."
        elif self._wallet is None:
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
            detail = (
                data.get("message")
                or data.get("error_message")
                or data.get("detail")
                or data.get("error")
            )
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
            "register_url": register_url
            if isinstance(register_url, str) and register_url
            else None,
            "pricing_url": pricing_url
            if isinstance(pricing_url, str) and pricing_url
            else None,
            "upgrade_message": upgrade_message
            if isinstance(upgrade_message, str) and upgrade_message
            else None,
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

    def _warn_anon_payment_required(
        self, price: Optional[str], response: httpx.Response
    ) -> None:
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
    email = _registration_email(email)
    headers = build_tracking_headers(
        source=_TRACKING_SOURCE,
        client=_TRACKING_CLIENT,
        version=__version__,
        tool="register_account",
    )
    headers["User-Agent"] = _USER_AGENT
    failure: Optional[str] = None
    try:
        with httpx.Client(
            base_url=base_url.rstrip("/"), transport=transport, timeout=timeout
        ) as http:
            response = http.post(
                "/api/agent/register", json={"email": email}, headers=headers
            )
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
