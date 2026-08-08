"""The rules that decide whether this SDK is allowed to spend money.

Holding a funded key is not the same as consenting to spend it, and the gap
between those two is where an autonomous caller loses money. A wallet is a
*capability*; this module is the *policy* — the separate, inspectable answer to
"under what circumstances, on what network, for which tools, up to how much".

Every check here runs **before** the wallet is handed a challenge, and the
reason is not defence in depth for its own sake:

* the wallet's own ``max_amount`` policy is enforced by the x402 library at
  signing time, in base units of whatever asset the offer names. A policy that
  cannot value the asset cannot cap it — which is why an unknown asset is
  refused here rather than signed. An offer denominated in an 18-decimal token
  looks a million times cheaper than the same number of USDC base units, and
  "$0.15" would settle as $150,000;
* per-session and per-day ceilings have no wallet-level equivalent at all. A
  per-call cap of $1 stops one bad offer and does nothing about a loop that
  takes it a thousand times.

The default is ``credits_only``. Nothing in this module can cause a payment
unless a caller has explicitly asked for ``x402_fallback``, and an ordinary
"out of Credits" 402 is never payable in either mode — it carries no
``accepts``, so there is no offer to evaluate in the first place.

**Budgets are charged before the paid retry is sent, and never refunded.**
Once a signed authorization leaves this process we do not know whether it
settled; a server that takes the payment and then times out, or answers 402
anyway, has still potentially moved the money. Counting optimistically would
let exactly that failure mode repeat until the ceiling is real.
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any, Iterable, Mapping, Optional

CREDITS_ONLY = "credits_only"
X402_FALLBACK = "x402_fallback"
PAYMENT_MODES = frozenset({CREDITS_ONLY, X402_FALLBACK})

# Assets this SDK is willing to value, by contract address, lowercased.
#
# The decimals are the load-bearing half: an offer's amount is an integer in
# the asset's base units and means nothing without them. An asset that is not
# in this table is refused rather than guessed at, because guessing wrong is
# not a rounding error — it is six orders of magnitude.
_KNOWN_ASSETS: dict[str, tuple[str, int]] = {
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USDC", 6),  # Base mainnet
    "0x036cbd53842c5426634e7929541ec2318f3dcf7e": ("USDC", 6),  # Base Sepolia
}

# Chain identifiers arrive spelled two ways depending on the x402 version that
# produced the challenge — a human name in v1, CAIP-2 in v2 — and both refer to
# the same chain. Normalising here means an allowlist written as {"base"} keeps
# working when a server upgrades its encoding.
_NETWORK_ALIASES: dict[str, str] = {
    "base": "base",
    "8453": "base",
    "eip155:8453": "base",
    "base-sepolia": "base-sepolia",
    "base sepolia": "base-sepolia",
    "84532": "base-sepolia",
    "eip155:84532": "base-sepolia",
}

_DEFAULT_ASSETS = frozenset({"USDC"})
_DEFAULT_NETWORKS = frozenset({"base"})


class PaymentPolicyError(ValueError):
    """The policy itself is not usable (bad mode, negative ceiling, ...)."""


def _money(value: Any, label: str) -> Optional[Decimal]:
    """Coerce a ceiling to Decimal. None means "no ceiling of this kind"."""
    if value is None:
        return None
    try:
        # str() first: Decimal(0.1) is 0.1000000000000000055511151231257827,
        # and a ceiling that is not the number the caller typed is a ceiling
        # they cannot reason about.
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PaymentPolicyError(f"{label} must be a number or None") from exc
    if amount < 0:
        raise PaymentPolicyError(f"{label} must not be negative")
    return amount


def _frozen(values: Optional[Iterable[str]]) -> Optional[frozenset[str]]:
    if values is None:
        return None
    return frozenset(str(value) for value in values)


def normalize_network(value: Any) -> Optional[str]:
    """Canonical chain name, or None when this is not a chain we recognise."""
    if not isinstance(value, str):
        return None
    return _NETWORK_ALIASES.get(value.strip().lower())


def resolve_asset(value: Any) -> Optional[tuple[str, int]]:
    """``(symbol, decimals)`` for an asset we can value, else None."""
    if not isinstance(value, str):
        return None
    return _KNOWN_ASSETS.get(value.strip().lower())


@dataclass(frozen=True)
class Offer:
    """One entry of a 402 challenge's ``accepts``, in terms we can reason about.

    ``amount`` is the *human* amount (USDC, not base units), which is the only
    form in which a budget comparison is meaningful.
    """

    scheme: str
    network: str
    asset_symbol: str
    amount: Decimal
    raw: Mapping[str, Any] = field(repr=False, default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - diagnostic aid
        return f"{self.amount:f} {self.asset_symbol} on {self.network}"


def parse_offers(body: Any) -> list[Offer]:
    """Read the offers out of a 402 body, dropping any we cannot value.

    Silently skipping the unreadable ones is deliberate: a challenge listing
    three ways to pay, one of them in an asset we do not know, should settle
    via one of the other two rather than fail outright.
    """
    if not isinstance(body, Mapping):
        return []
    entries = body.get("accepts")
    if not isinstance(entries, list):
        return []

    offers: list[Offer] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        network = normalize_network(entry.get("network"))
        asset = resolve_asset(entry.get("asset"))
        if network is None or asset is None:
            continue
        # `maxAmountRequired` is the v1 spelling, `amount` the v2 one. Take the
        # larger of the two if both appear: the ceiling we are agreeing to is
        # the most that could be taken, not the least.
        candidates = []
        for key in ("maxAmountRequired", "amount"):
            raw = entry.get(key)
            if isinstance(raw, bool) or raw is None:
                continue
            try:
                candidates.append(Decimal(str(raw)))
            except (InvalidOperation, TypeError, ValueError):
                continue
        if not candidates:
            continue
        base_units = max(candidates)
        if base_units < 0:
            continue

        symbol, decimals = asset
        offers.append(
            Offer(
                scheme=str(entry.get("scheme") or ""),
                network=network,
                asset_symbol=symbol,
                amount=base_units / (Decimal(10) ** decimals),
                raw=entry,
            )
        )
    return offers


def _offer_count(body: Any) -> int:
    """How many offers the server sent, readable or not."""
    if not isinstance(body, Mapping):
        return 0
    entries = body.get("accepts")
    return len(entries) if isinstance(entries, list) else 0


@dataclass(frozen=True)
class PaymentPolicy:
    """What this client may spend, and on what.

    Args:
        mode: ``credits_only`` (default — never pays) or ``x402_fallback``.
        max_payment_per_call: Ceiling for a single offer, in USD.
        max_payment_per_session: Ceiling for the lifetime of one client object.
        max_payment_per_day: Ceiling per UTC calendar day.
        allowed_payment_assets: Asset symbols that may be spent. An offer in
            anything else — including an asset whose decimals are unknown — is
            refused, since an amount that cannot be valued cannot be capped.
        allowed_networks: Chains that may be settled on, canonical names.
        x402_allowed_tools: Tool names that may be paid for; None means every
            tool. Matched against the SDK's own name for the call, never
            against a string supplied by the server.

    ``None`` removes a ceiling. That is a real option — some deployments cap in
    the wallet or upstream instead — but it is never the default: an agent that
    can retry is an agent that can retry a thousand times.
    """

    mode: str = CREDITS_ONLY
    max_payment_per_call: Optional[Decimal] = Decimal("1.00")
    max_payment_per_session: Optional[Decimal] = Decimal("5.00")
    max_payment_per_day: Optional[Decimal] = Decimal("20.00")
    allowed_payment_assets: frozenset[str] = _DEFAULT_ASSETS
    allowed_networks: frozenset[str] = _DEFAULT_NETWORKS
    x402_allowed_tools: Optional[frozenset[str]] = None

    def __post_init__(self) -> None:
        mode = str(self.mode).strip().lower()
        if mode not in PAYMENT_MODES:
            raise PaymentPolicyError(
                f"payment_mode must be one of {sorted(PAYMENT_MODES)}, not {self.mode!r}"
            )
        object.__setattr__(self, "mode", mode)
        object.__setattr__(
            self, "max_payment_per_call", _money(self.max_payment_per_call, "max_payment_per_call")
        )
        object.__setattr__(
            self,
            "max_payment_per_session",
            _money(self.max_payment_per_session, "max_payment_per_session"),
        )
        object.__setattr__(
            self, "max_payment_per_day", _money(self.max_payment_per_day, "max_payment_per_day")
        )
        object.__setattr__(
            self,
            "allowed_payment_assets",
            frozenset(str(a).strip().upper() for a in self.allowed_payment_assets),
        )
        networks = set()
        for value in self.allowed_networks:
            canonical = normalize_network(value)
            if canonical is None:
                raise PaymentPolicyError(f"unknown network in allowed_networks: {value!r}")
            networks.add(canonical)
        object.__setattr__(self, "allowed_networks", frozenset(networks))
        object.__setattr__(self, "x402_allowed_tools", _frozen(self.x402_allowed_tools))

    @property
    def pays(self) -> bool:
        return self.mode == X402_FALLBACK

    def with_mode(self, mode: str) -> "PaymentPolicy":
        return replace(self, mode=mode)

    def allows_tool(self, tool_name: Optional[str]) -> bool:
        if self.x402_allowed_tools is None:
            return True
        # An unnamed call cannot be checked against an allowlist, and "cannot
        # be checked" resolves to "not allowed" wherever money is involved.
        return bool(tool_name) and tool_name in self.x402_allowed_tools


class PaymentBudget:
    """Running spend for one client: session total, and per-UTC-day total.

    Charged before a payment is attempted and never credited back — see this
    module's docstring for why an optimistic ledger is the wrong shape here.
    """

    def __init__(self, *, clock=None) -> None:
        self._clock = clock or (lambda: _datetime.datetime.now(_datetime.timezone.utc))
        self._lock = RLock()
        self._session_spent = Decimal(0)
        self._day_spent = Decimal(0)
        self._day = self._today()

    def _today(self) -> _datetime.date:
        return self._clock().date()

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._day_spent = Decimal(0)

    @property
    def session_spent(self) -> Decimal:
        with self._lock:
            return self._session_spent

    @property
    def day_spent(self) -> Decimal:
        with self._lock:
            self._roll()
            return self._day_spent

    def would_exceed(self, amount: Decimal, policy: PaymentPolicy) -> Optional[str]:
        """The ceiling this amount would breach, or None if it fits."""
        with self._lock:
            self._roll()
            if (
                policy.max_payment_per_session is not None
                and self._session_spent + amount > policy.max_payment_per_session
            ):
                return (
                    f"session budget exhausted "
                    f"({self._session_spent:f}/{policy.max_payment_per_session:f} USD spent)"
                )
            if (
                policy.max_payment_per_day is not None
                and self._day_spent + amount > policy.max_payment_per_day
            ):
                return (
                    f"daily budget exhausted "
                    f"({self._day_spent:f}/{policy.max_payment_per_day:f} USD spent today)"
                )
            return None

    def charge(self, amount: Decimal) -> None:
        with self._lock:
            self._roll()
            self._session_spent += amount
            self._day_spent += amount

    def summary(self, policy: PaymentPolicy) -> dict:
        with self._lock:
            self._roll()
            return {
                "mode": policy.mode,
                "session_spent_usd": str(self._session_spent),
                "day_spent_usd": str(self._day_spent),
                "max_payment_per_call_usd": _optional_str(policy.max_payment_per_call),
                "max_payment_per_session_usd": _optional_str(policy.max_payment_per_session),
                "max_payment_per_day_usd": _optional_str(policy.max_payment_per_day),
                "day": self._day.isoformat(),
            }


def _optional_str(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


@dataclass(frozen=True)
class PaymentDecision:
    """Whether to pay, and — either way — the reason, in words.

    The refusal reason is carried rather than dropped because it is the only
    thing that tells a caller apart the two ways nothing happened: "the server
    offered nothing payable" and "the server offered something and your policy
    said no". Those have completely different fixes.
    """

    offer: Optional[Offer]
    reason: str

    @property
    def pay(self) -> bool:
        return self.offer is not None


def decide(
    body: Any,
    *,
    tool_name: Optional[str],
    policy: PaymentPolicy,
    budget: PaymentBudget,
    has_wallet: bool,
    x402_disabled_reason: Optional[str] = None,
) -> PaymentDecision:
    """Pick the first offer this policy permits, or explain the refusal.

    Order matters only for readability of the reason — every check is a veto.
    The cheap, local, always-true-or-false ones come first so that a caller in
    ``credits_only`` never even sees the offers parsed.
    """
    if not policy.pays:
        return PaymentDecision(
            None,
            "payment_mode is credits_only; pass payment_mode='x402_fallback' to allow paying",
        )
    if x402_disabled_reason:
        return PaymentDecision(None, f"x402 fallback is disabled for this client: {x402_disabled_reason}")
    if not has_wallet:
        # Safety requirement, stated separately from the mode check because it
        # is a different failure: the caller asked to pay and has nothing to
        # pay with. Never attempt, never raise from inside the wallet.
        return PaymentDecision(None, "no wallet is configured")
    if not policy.allows_tool(tool_name):
        return PaymentDecision(
            None, f"{tool_name or 'this call'} is not in x402_allowed_tools"
        )

    offers = parse_offers(body)
    # Offers dropped by `parse_offers` — an unrecognised chain, an asset whose
    # decimals we do not know — have no `Offer` to explain themselves with, and
    # would otherwise vanish from the reason entirely. Counting them is what
    # tells a caller "the server did offer something, this client just could
    # not read it" rather than leaving them to conclude the server sent
    # nothing.
    unusable = _offer_count(body) - len(offers)
    if not offers:
        return PaymentDecision(None, "the response carries no offer this client can value")

    refusals: list[str] = []
    if unusable:
        refusals.append(
            f"{unusable} offer(s) named an asset or network this client cannot value"
        )
    # **Cheapest first, not list order.** A ceiling bounds the worst case and
    # says nothing about the gap between the worst acceptable price and the
    # best one. Taking the first offer that fits hands whoever writes the
    # challenge a lever: every offer under the cap is equally acceptable, so
    # the dearest one wins simply by being listed first. Sorting removes the
    # lever, and costs the caller nothing — they asked to spend *at most* the
    # ceiling, never to spend it.
    for offer in sorted(offers, key=lambda candidate: candidate.amount):
        if offer.network not in policy.allowed_networks:
            refusals.append(f"network {offer.network} is not allowed")
            continue
        if offer.asset_symbol not in policy.allowed_payment_assets:
            refusals.append(f"asset {offer.asset_symbol} is not allowed")
            continue
        if (
            policy.max_payment_per_call is not None
            and offer.amount > policy.max_payment_per_call
        ):
            refusals.append(
                f"{offer.amount:f} {offer.asset_symbol} exceeds max_payment_per_call "
                f"({policy.max_payment_per_call:f})"
            )
            continue
        exceeded = budget.would_exceed(offer.amount, policy)
        if exceeded:
            refusals.append(exceeded)
            continue
        return PaymentDecision(offer, f"paying {offer}")

    return PaymentDecision(None, "; ".join(refusals))


__all__ = [
    "CREDITS_ONLY",
    "PAYMENT_MODES",
    "X402_FALLBACK",
    "Offer",
    "PaymentBudget",
    "PaymentDecision",
    "PaymentPolicy",
    "PaymentPolicyError",
    "decide",
    "normalize_network",
    "parse_offers",
    "resolve_asset",
]
