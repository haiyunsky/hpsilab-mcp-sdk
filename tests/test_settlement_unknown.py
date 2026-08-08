"""The client's half of "never pay twice for one call".

The API's half shipped first: an unresolved settlement comes back as a 502 with
`settlement_status: "unknown"`, no `accepts`, and a `call_id`, and the ledger is
unique on that id. None of it holds if the client walks away and starts over —
a fresh request gets a fresh id, a fresh challenge, a fresh nonce, and pays
again for work that may already have been paid for.

So there are three things here, and they are one rule seen from three angles:

* the client sends `X-Request-Id`, which is what makes the API's uniqueness
  constraint apply to a *retry* rather than only to a replay;
* an unresolved settlement is not a `HpsiMcpAPIError`, so the ordinary
  `except HpsiMcpAPIError: retry()` cannot swallow it;
* the client stops paying afterwards and remembers which calls are unresolved.
"""
from __future__ import annotations

import httpx
import pytest

from hpsilab_mcp import (
    HpsiMcpAPIError,
    HpsiMcpClient,
    HpsiMcpError,
    HpsiMcpSettlementUnknownError,
)

CHALLENGE = {
    "x402Version": 1,
    "tool": "get_iv_radar",
    "price": "$0.05",
    "accepts": [
        {
            "scheme": "exact",
            "network": "eip155:8453",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "maxAmountRequired": "50000",
            "payTo": "0x" + "1" * 40,
        }
    ],
}

UNKNOWN = {
    "error": "settlement_unknown",
    "message": (
        "The payment may have completed and this call could not be confirmed. "
        "Do not pay again — quote call_id call_abc123 for reconciliation."
    ),
    "call_id": "call_abc123",
    "tool": "get_iv_radar",
    "settlement_status": "unknown",
    "retryable": False,
}


class _Wallet:
    """Signs whatever it is shown, and counts how often."""

    def __init__(self) -> None:
        self.signatures = 0

    def sign(self, challenge):
        self.signatures += 1
        return {"X-PAYMENT": "signed"}, challenge.json()["accepts"][0]


def _client(handler, wallet=None):
    return HpsiMcpClient(
        wallet=wallet or _Wallet(),
        payment_mode="x402_fallback",
        transport=httpx.MockTransport(handler),
    )


def _pay_then(second_status: int, second_body: dict, seen: list | None = None):
    """402 on the unpaid attempt, `second_body` once payment is presented."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.headers.get("X-PAYMENT"):
            return httpx.Response(second_status, json=second_body)
        return httpx.Response(402, json=CHALLENGE)

    return handler


# --------------------------------------------------------------------------- #
# One logical call, one id
# --------------------------------------------------------------------------- #


class TestTheCallIdReachesTheAPI:
    def test_the_paid_retry_carries_the_same_id_as_the_quote(self):
        """The API threads one id through quote → pay → settle. Two ids would
        make the paid attempt look like a different call from the one that was
        quoted, and its uniqueness constraint would have nothing to bite on."""
        seen: list[httpx.Request] = []
        with _client(_pay_then(200, {"ok": True}, seen)) as client:
            client.get_iv_radar("NVDA")

        assert len(seen) == 2
        quote, paid = seen
        assert quote.headers["X-Request-Id"]
        assert paid.headers["X-Request-Id"] == quote.headers["X-Request-Id"]

    def test_separate_calls_get_separate_ids(self):
        """A shared id would be worse than none: the second paid call would
        collide with the first in the API's ledger and be refused."""
        seen: list[httpx.Request] = []
        with _client(_pay_then(200, {"ok": True}, seen)) as client:
            client.get_iv_radar("NVDA")
            client.get_iv_radar("AMD")

        ids = {request.headers["X-Request-Id"] for request in seen}
        assert len(ids) == 2

    def test_a_pinned_header_does_not_become_every_calls_id(self):
        """`headers={"X-Request-Id": ...}` at construction is a client-wide
        default; letting it through would give every paid call the same id."""
        seen: list[httpx.Request] = []
        client = HpsiMcpClient(
            wallet=_Wallet(),
            payment_mode="x402_fallback",
            headers={"X-Request-Id": "pinned-for-every-call"},
            transport=httpx.MockTransport(_pay_then(200, {"ok": True}, seen)),
        )
        with client:
            client.get_iv_radar("NVDA")
            client.get_iv_radar("AMD")

        assert all(r.headers["X-Request-Id"] != "pinned-for-every-call" for r in seen)
        assert len({r.headers["X-Request-Id"] for r in seen}) == 2


# --------------------------------------------------------------------------- #
# What an unresolved settlement raises
# --------------------------------------------------------------------------- #


class TestItCannotBeCaughtAsAnOrdinaryAPIError:
    def test_it_is_not_an_api_error(self):
        """The whole point. `except HpsiMcpAPIError: retry()` is the most
        ordinary line a caller writes, and for this one response it is the line
        that pays twice."""
        with _client(_pay_then(502, UNKNOWN)) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")

        assert not issubclass(HpsiMcpSettlementUnknownError, HpsiMcpAPIError)

    def test_it_is_still_an_sdk_error(self):
        """A caller catching everything this SDK raises must not have to name
        it separately to keep working."""
        assert issubclass(HpsiMcpSettlementUnknownError, HpsiMcpError)

    def test_a_generic_api_error_handler_does_not_swallow_it(self):
        with _client(_pay_then(502, UNKNOWN)) as client:
            try:
                client.get_iv_radar("NVDA")
            except HpsiMcpAPIError:  # pragma: no cover - the failure being tested
                pytest.fail("an unresolved settlement was caught as a retryable API error")
            except HpsiMcpSettlementUnknownError as exc:
                assert exc.call_id == "call_abc123"

    def test_it_carries_what_reconciliation_needs(self):
        with _client(_pay_then(502, UNKNOWN)) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError) as raised:
                client.get_iv_radar("NVDA")

        error = raised.value
        assert error.call_id == "call_abc123"
        assert error.tool == "get_iv_radar"
        assert error.settlement_status == "unknown"
        assert error.status_code == 502
        assert "not pay again" in str(error).lower()

    def test_the_status_code_is_not_what_identifies_it(self):
        """Keyed on the body, so a transport that reports it differently is
        still understood — and so a plain 502 from a proxy is not mistaken for
        a payment that may have settled."""
        with _client(_pay_then(500, UNKNOWN)) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")

    def test_an_ordinary_server_error_is_still_an_api_error(self):
        with _client(_pay_then(502, {"error": "upstream unavailable"})) as client:
            with pytest.raises(HpsiMcpAPIError):
                client.get_iv_radar("NVDA")


# --------------------------------------------------------------------------- #
# What the client does next
# --------------------------------------------------------------------------- #


class TestTheClientStopsPaying:
    def test_the_wallet_signs_once_and_only_once(self):
        wallet = _Wallet()
        with _client(_pay_then(502, UNKNOWN), wallet=wallet) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")

        assert wallet.signatures == 1

    def test_a_caller_that_retries_anyway_does_not_pay_again(self):
        """The defence that matters, because the caller controls the retry and
        we do not. The second call may fail — it must not spend."""
        wallet = _Wallet()
        with _client(_pay_then(502, UNKNOWN), wallet=wallet) as client:
            for _ in range(3):
                with pytest.raises(HpsiMcpError):
                    client.get_iv_radar("NVDA")

        assert wallet.signatures == 1

    def test_the_reason_is_reported(self):
        with _client(_pay_then(502, UNKNOWN)) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")
            summary = client.payment_spend_summary()

        assert "could not confirm" in summary["x402_disabled_reason"]

    def test_the_unresolved_call_is_remembered(self):
        with _client(_pay_then(502, UNKNOWN)) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")
            summary = client.payment_spend_summary()

        assert summary["unresolved_settlements"] == {"call_abc123": "get_iv_radar"}

    def test_the_amount_stays_spent(self):
        """It may have moved. Crediting it back would let the same budget pay
        for it a second time."""
        with _client(_pay_then(502, UNKNOWN)) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")
            summary = client.payment_spend_summary()

        assert float(summary["session_spent_usd"]) > 0

    def test_a_connection_failure_after_paying_is_recorded_the_same_way(self):
        """The other way an outcome goes unknown: the answer never arrives. It
        already stopped the client paying; what it lacked was the call_id."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("X-PAYMENT"):
                raise httpx.ConnectTimeout("no answer")
            return httpx.Response(402, json=CHALLENGE)

        with _client(handler) as client:
            with pytest.raises(HpsiMcpError):
                client.get_iv_radar("NVDA")
            summary = client.payment_spend_summary()

        assert len(summary["unresolved_settlements"]) == 1
        assert next(iter(summary["unresolved_settlements"])).startswith("call_")

    def test_the_record_survives_reopening_the_x402_path(self):
        """`set_wallet` is the repair after reconciliation. Forgetting what was
        unresolved is not part of repairing it."""
        with _client(_pay_then(502, UNKNOWN)) as client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")
            client.set_wallet(_Wallet())
            summary = client.payment_spend_summary()

        assert summary["x402_disabled_reason"] is None
        assert summary["unresolved_settlements"] == {"call_abc123": "get_iv_radar"}


class TestCreditsKeepWorking:
    def test_an_unresolved_payment_does_not_break_the_api_key(self):
        """Only the x402 path latches. Nothing about the credential failed, and
        a client that stops answering entirely is a worse outcome than one that
        stops paying."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if request.headers.get("X-PAYMENT"):
                return httpx.Response(502, json=UNKNOWN)
            if calls["n"] <= 2:
                return httpx.Response(402, json=CHALLENGE)
            return httpx.Response(200, json={"ok": True})

        client = HpsiMcpClient(
            api_key="hpsi_test_key",
            wallet=_Wallet(),
            payment_mode="x402_fallback",
            transport=httpx.MockTransport(handler),
        )
        with client:
            with pytest.raises(HpsiMcpSettlementUnknownError):
                client.get_iv_radar("NVDA")
            assert client.get_iv_radar("AMD") == {"ok": True}
