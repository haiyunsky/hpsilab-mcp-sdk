"""Phase C: the SDK as a controlled automatic x402 client.

Every test here is about *not* spending money, which is the asymmetry that
shapes the whole module: a client that fails to pay when it should have loses
one call, and a client that pays when it should not have loses funds and cannot
get them back. So the interesting cases are all refusals, and the two payments
that do happen are here to prove the refusals are not simply "never pays".

The four DoD items from the engineering spec have a test each, marked below.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from hpsilab_mcp import HpsiMcpClient, PaymentPolicy
from hpsilab_mcp.errors import HpsiMcpInsufficientCreditsError, HpsiMcpPaymentError
from hpsilab_mcp.policy import (
    CREDITS_ONLY,
    X402_FALLBACK,
    PaymentBudget,
    PaymentPolicyError,
    decide,
    parse_offers,
)

KEY = "hpsi_live_key"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def challenge(amount: str = "100000", *, network: str = "eip155:8453", asset: str = USDC_BASE):
    """A 402 carrying one settleable offer. 100000 base units of USDC = $0.10."""
    entry = {"scheme": "exact", "network": network, "maxAmountRequired": amount, "payTo": "0x" + "1" * 40}
    if asset is not None:
        entry["asset"] = asset
    return {"x402Version": 1, "error": "X-PAYMENT header is required", "accepts": [entry], "tool": "get_monte_carlo"}


# The ordinary Credits refusal: same status, no `accepts`, never payable.
REFUSAL = {
    "error": "insufficient_credits",
    "message": "This call costs 5 Credits and 1 remain.",
    "credits_required": 5,
    "credits_remaining": 1,
}


class Wallet:
    """Stands in for X402Wallet — the real one needs the optional [x402] extra."""

    def __init__(self, error=None):
        self.calls = 0
        self._error = error

    def payment_headers(self, response):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return {"X-PAYMENT": "signed-authorization"}


def client_for(*responses, wallet=None, **kwargs):
    queue = list(responses)

    def handler(request):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=wallet, **kwargs)


# ---------------------------------------------------------------------------
# DoD 1 — an ordinary 402 never causes payment
# ---------------------------------------------------------------------------


def test_a_credits_refusal_is_never_paid_even_in_fallback_mode():
    """The strongest form of the rule: opted in, funded, allowed — and still
    not paid, because a Credits refusal carries no offer to settle."""
    wallet = Wallet()
    c = client_for(
        httpx.Response(402, json=REFUSAL),
        wallet=wallet,
        api_key=KEY,
        payment_mode=X402_FALLBACK,
    )

    with pytest.raises(HpsiMcpInsufficientCreditsError):
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    assert c.payment_spend_summary()["session_spent_usd"] == "0"
    c.close()


def test_credits_only_is_the_default_for_a_keyed_client_with_an_ambient_wallet(monkeypatch):
    """A private key left in the environment by another project is not consent.

    This is the behaviour change Phase C makes: the SDK used to treat any
    readable `HPSILAB_X402_PRIVATE_KEY` as permission to spend.
    """
    wallet = Wallet()
    monkeypatch.setattr("hpsilab_mcp.client.wallet_from_env", lambda: wallet)

    c = client_for(httpx.Response(402, json=challenge()), api_key=KEY)

    assert c.payment_policy.mode == CREDITS_ONLY
    with pytest.raises(HpsiMcpPaymentError) as caught:
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    assert "credits_only" in str(caught.value)
    c.close()


def test_an_env_wallet_is_consent_when_it_is_the_only_credential(monkeypatch):
    """A keyless client has nothing else to pay with, so the same ambient key
    is unambiguous there — refusing would leave a client that cannot work."""
    wallet = Wallet()
    monkeypatch.setattr("hpsilab_mcp.client.wallet_from_env", lambda: wallet)

    c = client_for(httpx.Response(402, json=challenge()), httpx.Response(200, json={"ok": True}))

    assert c.payment_policy.mode == X402_FALLBACK
    c.close()


def test_passing_a_wallet_in_code_is_consent():
    """Nobody writes `wallet=X402Wallet(...)` by accident."""
    c = client_for(httpx.Response(200, json={}), wallet=Wallet(), api_key=KEY)

    assert c.payment_policy.mode == X402_FALLBACK
    c.close()


def test_an_explicit_mode_overrides_the_wallet_it_was_given():
    c = client_for(httpx.Response(200, json={}), wallet=Wallet(), api_key=KEY, payment_mode=CREDITS_ONLY)

    assert c.payment_policy.mode == CREDITS_ONLY
    c.close()


# ---------------------------------------------------------------------------
# DoD 2 — a valid opt-in challenge completes one paid request
# ---------------------------------------------------------------------------


def test_an_opted_in_client_pays_once_and_gets_the_result():
    seen = []

    def handler(request):
        seen.append(request.headers.get("X-PAYMENT"))
        if len(seen) == 1:
            return httpx.Response(402, json=challenge())
        return httpx.Response(200, json={"symbol": "NVDA", "paid": True})

    wallet = Wallet()
    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=wallet, api_key=KEY, payment_mode=X402_FALLBACK
    )

    assert c.get_monte_carlo("NVDA") == {"symbol": "NVDA", "paid": True}
    assert wallet.calls == 1
    assert seen == [None, "signed-authorization"]
    assert c.payment_spend_summary()["session_spent_usd"] == "0.1"
    c.close()


def test_a_free_call_never_reaches_the_wallet():
    wallet = Wallet()
    c = client_for(httpx.Response(200, json={"ok": True}), wallet=wallet, api_key=KEY)

    c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    c.close()


# ---------------------------------------------------------------------------
# DoD 3 — an invalid signer closes the x402 circuit immediately
# ---------------------------------------------------------------------------


def test_an_invalid_signer_closes_x402_and_is_not_asked_twice():
    wallet = Wallet(error=ValueError("no scheme for this network"))
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=wallet, api_key=KEY, payment_mode=X402_FALLBACK
    )

    for _ in range(3):
        with pytest.raises(HpsiMcpPaymentError):
            c.get_monte_carlo("NVDA")

    assert wallet.calls == 1, "the broken signer must be asked once, not once per call"
    c.close()


def test_a_stuck_server_closes_x402_without_bricking_the_client():
    """A server that takes the payment and answers 402 anyway would drain the
    wallet one call at a time. Closing x402 stops that; closing the whole
    client — which is what used to happen — also stops the Credits-funded calls
    that were working fine."""

    def handler(request):
        if request.url.path.endswith("/monte_carlo/NVDA"):
            return httpx.Response(402, json=challenge())
        return httpx.Response(200, json={"free": True})

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=Wallet(), api_key=KEY, payment_mode=X402_FALLBACK
    )

    with pytest.raises(HpsiMcpPaymentError):
        c.get_monte_carlo("NVDA")

    assert c._x402_disabled_reason is not None
    assert c._auth_failed is False
    assert c.get_ai_prediction("NVDA") == {"free": True}
    c.close()


def test_swapping_the_wallet_reopens_x402_but_does_not_grant_consent():
    """Repairing a wallet is a repair. It must not promote a `credits_only`
    client into one that spends."""
    c = client_for(httpx.Response(200, json={}), wallet=Wallet(), api_key=KEY, payment_mode=CREDITS_ONLY)
    c._x402_disabled_reason = "an earlier failure"

    c.set_wallet(Wallet())

    assert c._x402_disabled_reason is None
    assert c.payment_policy.mode == CREDITS_ONLY
    c.close()


# ---------------------------------------------------------------------------
# DoD 4 — a retry does not double pay
# ---------------------------------------------------------------------------


def test_one_logical_call_signs_at_most_once():
    wallet = Wallet()
    c = client_for(
        httpx.Response(402, json=challenge()),
        wallet=wallet,
        api_key=KEY,
        payment_mode=X402_FALLBACK,
    )

    with pytest.raises(HpsiMcpPaymentError):
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 1
    c.close()


def test_an_unfinished_payment_stops_further_paying():
    """The retry left with a signed authorization and never came back. Whether
    it settled is unknowable from here, so the next 402 must not sign again."""
    wallet = Wallet()
    calls = []

    def handler(request):
        calls.append(request.headers.get("X-PAYMENT"))
        if calls[-1] is not None:
            raise httpx.ConnectTimeout("gone")
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=wallet, api_key=KEY, payment_mode=X402_FALLBACK
    )

    with pytest.raises(Exception):
        c.get_monte_carlo("NVDA")

    assert c._x402_disabled_reason is not None
    # And the money is treated as gone, because it might be.
    assert c.payment_spend_summary()["session_spent_usd"] == "0.1"

    with pytest.raises(HpsiMcpPaymentError):
        c.get_monte_carlo("NVDA")
    assert wallet.calls == 1
    c.close()


# ---------------------------------------------------------------------------
# The policy surface
# ---------------------------------------------------------------------------


def test_an_offer_over_the_per_call_ceiling_is_not_signed():
    wallet = Wallet()
    c = client_for(
        httpx.Response(402, json=challenge("5000000")),  # $5.00
        wallet=wallet,
        api_key=KEY,
        payment_policy=PaymentPolicy(mode=X402_FALLBACK, max_payment_per_call="1.00"),
    )

    with pytest.raises(HpsiMcpPaymentError) as caught:
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    assert "max_payment_per_call" in str(caught.value)
    c.close()


def test_the_session_ceiling_stops_a_loop_the_per_call_ceiling_cannot():
    """$0.10 a call is under any sane per-call cap; a hundred of them is not.
    This ceiling has no wallet-level equivalent, which is why it exists here."""
    wallet = Wallet()

    def handler(request):
        if request.headers.get("X-PAYMENT"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler),
        wallet=wallet,
        api_key=KEY,
        payment_policy=PaymentPolicy(mode=X402_FALLBACK, max_payment_per_session="0.25"),
    )

    assert c.get_monte_carlo("NVDA") == {"ok": True}
    assert c.get_monte_carlo("NVDA") == {"ok": True}

    with pytest.raises(HpsiMcpPaymentError) as caught:
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 2
    assert "session budget exhausted" in str(caught.value)
    c.close()


def test_the_daily_ceiling_is_per_utc_day():
    import datetime

    policy = PaymentPolicy(mode=X402_FALLBACK, max_payment_per_day="1.00", max_payment_per_session=None)
    clock = [datetime.datetime(2026, 8, 8, 23, 0, tzinfo=datetime.timezone.utc)]
    budget = PaymentBudget(clock=lambda: clock[0])

    budget.charge(Decimal("0.90"))
    assert budget.would_exceed(Decimal("0.50"), policy) is not None

    clock[0] = datetime.datetime(2026, 8, 9, 1, 0, tzinfo=datetime.timezone.utc)
    assert budget.would_exceed(Decimal("0.50"), policy) is None
    # The session total is not a daily total and must not roll over with it.
    assert budget.session_spent == Decimal("0.90")


def test_a_tool_outside_the_allowlist_is_not_paid_for():
    wallet = Wallet()
    c = client_for(
        httpx.Response(402, json=challenge()),
        wallet=wallet,
        api_key=KEY,
        payment_policy=PaymentPolicy(mode=X402_FALLBACK, x402_allowed_tools={"get_iv_radar"}),
    )

    with pytest.raises(HpsiMcpPaymentError) as caught:
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    assert "x402_allowed_tools" in str(caught.value)
    c.close()


def test_the_allowlist_is_matched_against_our_own_name_for_the_call():
    """The offer's `description` is a string the server chose. Trusting it would
    let a server route a call past an allowlist by relabelling its own offer."""
    wallet = Wallet()
    body = challenge()
    body["accepts"][0]["description"] = "get_iv_radar"
    body["tool"] = "get_iv_radar"

    c = client_for(
        httpx.Response(402, json=body),
        wallet=wallet,
        api_key=KEY,
        payment_policy=PaymentPolicy(mode=X402_FALLBACK, x402_allowed_tools={"get_iv_radar"}),
    )

    with pytest.raises(HpsiMcpPaymentError):
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    c.close()


def test_an_offer_on_an_unlisted_network_is_not_paid_for():
    wallet = Wallet()
    c = client_for(
        httpx.Response(402, json=challenge(network="eip155:84532")),  # Base Sepolia
        wallet=wallet,
        api_key=KEY,
        payment_policy=PaymentPolicy(mode=X402_FALLBACK, allowed_networks={"base"}),
    )

    with pytest.raises(HpsiMcpPaymentError) as caught:
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    assert "network base-sepolia is not allowed" in str(caught.value)
    c.close()


def test_an_asset_we_cannot_value_is_never_signed():
    """The failure this prevents is not a refusal, it is a 10^12 overpayment: an
    amount is an integer in the asset's base units, so reading 150000 units of
    an 18-decimal token as if it were USDC turns $0.15 into $150,000."""
    wallet = Wallet()
    unknown = "0x" + "a" * 40
    c = client_for(
        httpx.Response(402, json=challenge(asset=unknown)),
        wallet=wallet,
        api_key=KEY,
        payment_mode=X402_FALLBACK,
    )

    with pytest.raises(HpsiMcpPaymentError):
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0
    c.close()


def test_an_offer_with_no_asset_at_all_is_not_valued_either():
    assert parse_offers(challenge(asset=None)) == []


def test_the_first_offer_that_fits_is_the_one_taken():
    body = challenge()
    body["accepts"] = [
        {"scheme": "exact", "network": "eip155:1", "asset": USDC_BASE, "maxAmountRequired": "100000"},
        {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE, "maxAmountRequired": "5000000"},
        {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE, "maxAmountRequired": "150000"},
    ]

    decision = decide(
        body,
        tool_name="get_monte_carlo",
        policy=PaymentPolicy(mode=X402_FALLBACK, max_payment_per_call="1.00"),
        budget=PaymentBudget(),
        has_wallet=True,
    )

    assert decision.pay
    assert decision.offer.amount == Decimal("0.15")


def test_the_refusal_reason_names_every_offer_it_turned_down():
    """One reason per offer, because "nothing worked" is not actionable when
    three different things went wrong — including the offer that was dropped
    before it could be judged, which would otherwise vanish from the account
    and leave the caller thinking the server sent one fewer than it did."""
    body = challenge()
    body["accepts"] = [
        {"scheme": "exact", "network": "eip155:1", "asset": USDC_BASE, "maxAmountRequired": "100000"},
        {"scheme": "exact", "network": "eip155:84532", "asset": USDC_BASE, "maxAmountRequired": "100000"},
        {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE, "maxAmountRequired": "5000000"},
    ]

    decision = decide(
        body,
        tool_name="get_monte_carlo",
        policy=PaymentPolicy(mode=X402_FALLBACK, max_payment_per_call="1.00"),
        budget=PaymentBudget(),
        has_wallet=True,
    )

    assert not decision.pay
    assert "1 offer(s) named an asset or network this client cannot value" in decision.reason
    assert "network base-sepolia is not allowed" in decision.reason
    assert "max_payment_per_call" in decision.reason


def test_a_missing_wallet_never_reaches_a_payment_attempt():
    decision = decide(
        challenge(),
        tool_name="get_monte_carlo",
        policy=PaymentPolicy(mode=X402_FALLBACK),
        budget=PaymentBudget(),
        has_wallet=False,
    )

    assert not decision.pay
    assert "no wallet" in decision.reason


# ---------------------------------------------------------------------------
# The policy object itself
# ---------------------------------------------------------------------------


def test_the_defaults_are_the_safe_ones():
    policy = PaymentPolicy()

    assert policy.mode == CREDITS_ONLY
    assert policy.pays is False
    assert policy.max_payment_per_call == Decimal("1.00")
    assert policy.max_payment_per_session == Decimal("5.00")
    assert policy.max_payment_per_day == Decimal("20.00")
    assert policy.allowed_payment_assets == frozenset({"USDC"})
    assert policy.allowed_networks == frozenset({"base"})


def test_a_ceiling_is_the_number_that_was_typed():
    """Decimal(0.1) is 0.1000000000000000055511151231257827. A ceiling a caller
    cannot reproduce is a ceiling they cannot reason about."""
    assert PaymentPolicy(max_payment_per_call=0.1).max_payment_per_call == Decimal("0.1")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "sometimes"},
        {"max_payment_per_call": -1},
        {"max_payment_per_day": "free"},
        {"allowed_networks": {"solana"}},
    ],
)
def test_an_unusable_policy_fails_at_construction_not_at_payment_time(kwargs):
    with pytest.raises(PaymentPolicyError):
        PaymentPolicy(**kwargs)


def test_replacing_the_policy_does_not_refund_what_was_spent():
    """Otherwise a $5 session ceiling is reachable twice by re-stating it."""
    wallet = Wallet()

    def handler(request):
        if request.headers.get("X-PAYMENT"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=wallet, api_key=KEY, payment_mode=X402_FALLBACK
    )
    c.get_monte_carlo("NVDA")

    c.set_payment_policy(PaymentPolicy(mode=X402_FALLBACK, max_payment_per_session="0.05"))

    assert c.payment_spend_summary()["session_spent_usd"] == "0.1"
    with pytest.raises(HpsiMcpPaymentError):
        c.get_monte_carlo("NVDA")
    c.close()


def test_the_spend_summary_never_carries_wallet_material():
    """It is the one payment structure meant to be logged."""
    c = client_for(httpx.Response(200, json={}), wallet=Wallet(), api_key=KEY)

    rendered = str(c.payment_spend_summary())

    assert "signed" not in rendered
    assert "0x" not in rendered
    c.close()


# ---------------------------------------------------------------------------
# A wallet is not a top-up for an account
# ---------------------------------------------------------------------------


def test_a_keyed_client_never_pays_when_credits_run_out():
    """The README used to show `api_key=` and `wallet=` together as if the
    wallet were a fallback for an exhausted balance. It is not, and the reason
    is server-side: the API does not offer x402 to a caller it can identify
    (`rate_limit._maybe_payment_challenge` returns the original refusal
    untouched for a signed-in subject; the MCP gate runs the tool as soon as
    `_real_account` resolves). What comes back is `insufficient_credits` — a
    402 with no `accepts` — so there is nothing to authorise.

    Worth a test rather than a comment: nothing in the SDK enforces this, and
    a future server change could start offering it. If that happens this test
    fails, which is the moment to update the documentation rather than years
    later.
    """
    wallet = Wallet()
    c = client_for(
        httpx.Response(402, json=REFUSAL),
        wallet=wallet,
        api_key=KEY,
        payment_mode=X402_FALLBACK,
    )

    with pytest.raises(HpsiMcpInsufficientCreditsError):
        c.get_monte_carlo("NVDA")

    assert wallet.calls == 0, "a Credits refusal must never reach the wallet"
    assert c.payment_spend_summary()["session_spent_usd"] == "0"
    c.close()


def test_the_same_client_without_a_key_does_pay():
    """The contrast that makes the rule legible: identical policy, identical
    wallet, and the only difference is whether the caller has an account."""
    wallet = Wallet()

    def handler(request):
        if request.headers.get("X-PAYMENT"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=wallet, payment_mode=X402_FALLBACK
    )

    assert c.get_monte_carlo("NVDA") == {"ok": True}
    assert wallet.calls == 1
    c.close()


# ---------------------------------------------------------------------------
# The ceiling bounds the worst price; it does not choose the best one
# ---------------------------------------------------------------------------


def test_the_cheapest_acceptable_offer_is_taken_not_the_first():
    """A challenge may list several offers, and every one under the ceiling is
    equally acceptable — so taking the first hands whoever writes the challenge
    a lever: order `accepts` dearest-first and the caller pays the most their
    policy allows. The ceiling was doing its job and still costing 18x."""
    body = challenge()
    body["accepts"] = [
        {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE,
         "maxAmountRequired": "900000", "payTo": "0x" + "1" * 40},   # $0.90
        {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE,
         "maxAmountRequired": "50000", "payTo": "0x" + "1" * 40},    # $0.05
        {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE,
         "maxAmountRequired": "150000", "payTo": "0x" + "1" * 40},   # $0.15
    ]

    decision = decide(
        body,
        tool_name="get_monte_carlo",
        policy=PaymentPolicy(mode=X402_FALLBACK, max_payment_per_call="1.00"),
        budget=PaymentBudget(),
        has_wallet=True,
    )

    assert decision.pay
    assert decision.offer.amount == Decimal("0.05")


def test_ordering_cannot_change_what_is_paid():
    """The same offers in any order must cost the same."""
    entries = [
        {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE,
         "maxAmountRequired": amount, "payTo": "0x" + "1" * 40}
        for amount in ("300000", "70000", "500000")
    ]
    chosen = set()
    for order in ([0, 1, 2], [2, 1, 0], [1, 0, 2]):
        body = challenge()
        body["accepts"] = [entries[i] for i in order]
        decision = decide(
            body, tool_name="get_monte_carlo",
            policy=PaymentPolicy(mode=X402_FALLBACK, max_payment_per_call="1.00"),
            budget=PaymentBudget(), has_wallet=True,
        )
        chosen.add(decision.offer.amount)

    assert chosen == {Decimal("0.07")}


# ---------------------------------------------------------------------------
# The wallet must sign the offer the policy approved
# ---------------------------------------------------------------------------


class SigningWallet:
    """A wallet that reports what it signed — and can be told to sign something
    other than what the policy picked."""

    def __init__(self, agreed=None):
        self.calls = 0
        self._agreed = agreed

    def sign(self, response):
        self.calls += 1
        body = response.json()
        agreed = self._agreed if self._agreed is not None else body["accepts"][0]
        return {"X-PAYMENT": "signed"}, agreed


def test_a_wallet_signing_a_different_offer_is_refused(monkeypatch):
    """`PaymentPolicy` picks one offer from `accepts` and the wallet picks one
    independently; the signature commits to the wallet's. Nothing made those
    the same choice, so they are compared before the payment leaves."""
    dearer = {"scheme": "exact", "network": "eip155:8453", "asset": USDC_BASE,
              "maxAmountRequired": "900000", "payTo": "0x" + "1" * 40}
    wallet = SigningWallet(agreed=dearer)
    sent = []

    def handler(request):
        sent.append(request.headers.get("X-PAYMENT"))
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=wallet, api_key=KEY,
        payment_mode=X402_FALLBACK,
    )

    with pytest.raises(HpsiMcpPaymentError):
        c.get_monte_carlo("NVDA")

    assert sent == [None], "the mismatched payment must never be sent"
    assert c._x402_disabled_reason is not None
    assert c.payment_spend_summary()["session_spent_usd"] == "0", (
        "a payment that was never sent must not be charged to the budget"
    )
    c.close()


def test_a_wallet_signing_the_approved_offer_goes_through():
    """The contrast — otherwise the check above passes by refusing everything."""
    wallet = SigningWallet()

    def handler(request):
        if request.headers.get("X-PAYMENT"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=wallet, api_key=KEY,
        payment_mode=X402_FALLBACK,
    )

    assert c.get_monte_carlo("NVDA") == {"ok": True}
    assert wallet.calls == 1
    assert c.payment_spend_summary()["session_spent_usd"] == "0.1"
    c.close()


def test_a_wallet_that_cannot_report_what_it_signed_still_works():
    """Refusing every wallet predating `sign()` would break paying clients to
    close a gap none of them have been shown to have."""
    legacy = Wallet()   # only `payment_headers`

    def handler(request):
        if request.headers.get("X-PAYMENT"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(402, json=challenge())

    c = HpsiMcpClient(
        transport=httpx.MockTransport(handler), wallet=legacy, api_key=KEY,
        payment_mode=X402_FALLBACK,
    )

    assert c.get_monte_carlo("NVDA") == {"ok": True}
    c.close()
