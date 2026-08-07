"""402 handling: what the client does when a call has to be paid for.

The signing itself belongs to the x402 library and needs a funded key, so the
wallet is stubbed here — these tests cover the client's part of the contract:
pay only when asked, retry exactly once, and otherwise hand the caller a
challenge they can act on.
"""

import unittest
import warnings

import httpx

from hpsilab_mcp import HpsiMcpClient
from hpsilab_mcp.errors import HpsiMcpConfigError, HpsiMcpPaymentError

CHALLENGE = {
    "x402Version": 2,
    "error": "Anonymous free quota for get_monte_carlo is exhausted.",
    "accepts": [
        {
            "scheme": "exact",
            "network": "eip155:8453",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "amount": "100000",
            "payTo": "0x0000000000000000000000000000000000000001",
        }
    ],
    "tool": "get_monte_carlo",
    "price": "$0.10",
}


class _StubWallet:
    """Stands in for X402Wallet without touching a key or the x402 stack."""

    def __init__(self, headers=None, error=None):
        self._headers = headers if headers is not None else {"PAYMENT-SIGNATURE": "signed-payload"}
        self._error = error
        self.calls = 0

    def payment_headers(self, response):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._headers


class PaymentFlowTests(unittest.TestCase):
    def test_402_with_an_account_but_no_wallet_suggests_paying_or_upgrading(self) -> None:
        """Reaching a 402 with `self._wallet is None` now always means a real
        api_key is set (construction requires api_key or wallet — see
        HpsiMcpClient.__init__) — an already-registered account whose quota
        this call exceeds, not an unidentified caller. The message should
        offer what's actually still available: pay per call, or upgrade.

        Raised as a payment error rather than a configuration one: the key is
        valid and the remedy is money. It used to surface as `HpsiMcpConfigError`
        because `_trip_auth_circuit` ran before the payment branch could, which
        also threw away the challenge the caller needed in order to pay."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=CHALLENGE)

        client = HpsiMcpClient(api_key="hpsi_real", transport=httpx.MockTransport(handler))

        with self.assertRaises(HpsiMcpPaymentError) as caught:
            client.get_monte_carlo("NVDA")

        error = caught.exception
        self.assertIn("HpsiMcpClient(wallet=X402Wallet(...))", str(error))
        self.assertIn("hpsilab.com/pricing", str(error))
        # The offer survives, so a caller with their own x402 client can settle it.
        self.assertTrue(error.accepts)
        client.close()

    def test_402_warns_a_wallet_only_caller_the_way_429_does(self) -> None:
        """The conversion hole found in the 2026-07-31 logs. `_raise_for_status`
        branches on 402 before 429, so crossing into overage used to *silence*
        the only human-visible prompt the SDK has — a caller's second session
        got a bare traceback recommending a crypto wallet and nothing else.
        No server-side wording can fix that: on this path nothing reads it.

        Uses a wallet-only client (no api_key): construction now requires an
        identity, and `self._api_key is None` — the warning's trigger
        condition — means exactly that, not "no identity at all" anymore."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=CHALLENGE)

        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=_StubWallet())

        with self.assertRaises(HpsiMcpConfigError):
            client.get_monte_carlo("NVDA")
        client.close()

    def test_402_warning_reads_flat_register_field_when_no_upgrade_dict(self) -> None:
        # A 402 challenge body carrying the newer flat `register` string
        # instead of (or in addition to) a nested `upgrade` object must still
        # steer the warning at the right URL.
        challenge = {**CHALLENGE, "register": "https://hpsilab.com/register?src=flat"}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=challenge)

        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=_StubWallet())

        with self.assertRaises(HpsiMcpConfigError):
            client.get_monte_carlo("NVDA")
        client.close()

    def test_402_stays_quiet_for_a_caller_with_its_own_key(self) -> None:
        """An account holder's 402 is a plan question, not an onboarding one —
        telling them to register would be noise. Mirrors the 429 branch."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=CHALLENGE)

        client = HpsiMcpClient(api_key="hpsi_real", transport=httpx.MockTransport(handler))

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpPaymentError):
                client.get_monte_carlo("NVDA")

        self.assertEqual([w for w in caught if "register_account" in str(w.message)], [])
        client.close()

    def test_wallet_pays_and_the_retry_carries_the_payment_header(self) -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("PAYMENT-SIGNATURE"))
            if len(seen) == 1:
                return httpx.Response(402, json=CHALLENGE)
            return httpx.Response(200, json={"symbol": "NVDA", "paid": True})

        wallet = _StubWallet()
        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=wallet)

        self.assertEqual(client.get_monte_carlo("NVDA"), {"symbol": "NVDA", "paid": True})
        self.assertEqual(wallet.calls, 1)
        self.assertEqual(seen, [None, "signed-payload"])
        client.close()

    def test_the_first_call_is_always_free(self) -> None:
        # No pre-emptive paying: a call that succeeds on the free quota must
        # never reach the wallet.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"symbol": "NVDA"})

        wallet = _StubWallet()
        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=wallet)

        client.get_monte_carlo("NVDA")

        self.assertEqual(wallet.calls, 0)
        client.close()

    def test_a_second_402_is_raised_rather_than_paid_again(self) -> None:
        # One retry, not a loop — a server that keeps answering 402 must not
        # be able to drain the wallet.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=CHALLENGE)

        wallet = _StubWallet()
        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=wallet)

        with self.assertRaises(HpsiMcpConfigError):
            client.get_monte_carlo("NVDA")

        self.assertEqual(wallet.calls, 1)
        client.close()

    def test_a_priced_call_does_not_disable_the_rest_of_the_client(self) -> None:
        """One tool being priced says nothing about the next one.

        This used to trip the auth breaker, so a keyed caller who hit a single
        Pro tool's paywall had every later call — including free tools —
        refused locally without ever reaching the network. The wallet-drain
        guard that the breaker exists for lives on the *post-payment* 402
        instead (see `test_a_second_402_is_raised_rather_than_paid_again`),
        which is the only 402 that means "paying did not resolve this"."""
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if request.url.path.endswith("/monte_carlo/NVDA"):
                return httpx.Response(402, json=CHALLENGE)
            return httpx.Response(200, json={"symbol": "NVDA"})

        client = HpsiMcpClient(api_key="hpsi_real", transport=httpx.MockTransport(handler))
        with self.assertRaises(HpsiMcpPaymentError):
            client.get_monte_carlo("NVDA")

        # The next call still goes out, and succeeds.
        self.assertEqual(client.get_ai_prediction("NVDA"), {"symbol": "NVDA"})
        self.assertEqual(calls, 2)
        self.assertFalse(client._auth_failed)
        client.close()

    def test_a_refused_challenge_propagates_untouched(self) -> None:
        # e.g. the price is over max_price_usdc, or the network has no scheme.
        # The wallet's own error is the useful one; don't bury it under a
        # generic payment error.
        wallet = _StubWallet(error=ValueError("amount exceeds max_amount policy"))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=CHALLENGE)

        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=wallet)

        with self.assertRaises(HpsiMcpConfigError) as caught:
            client.get_monte_carlo("NVDA")
        self.assertIsNone(caught.exception.__cause__)
        self.assertNotIn("max_amount policy", str(caught.exception))
        client.close()

    def test_pro_tool_402_is_also_payable(self) -> None:
        challenge = {**CHALLENGE, "tool": "get_pretrade_risk_scan", "price": "$0.15"}
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if len(calls) == 1:
                return httpx.Response(402, json=challenge)
            return httpx.Response(200, json={"symbol": "NVDA", "risk": "ok"})

        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=_StubWallet())

        self.assertEqual(client.get_pretrade_risk_scan("NVDA"), {"symbol": "NVDA", "risk": "ok"})
        self.assertEqual(calls, ["/api/pretrade-risk-scan", "/api/pretrade-risk-scan"])
        client.close()


class WalletConstructionTests(unittest.TestCase):
    def test_env_var_is_the_only_implicit_source_of_a_wallet(self) -> None:
        # Without HPSILAB_X402_PRIVATE_KEY set, a client must never end up
        # holding a wallet it wasn't given.
        import os

        self.assertIsNone(os.environ.get("HPSILAB_X402_PRIVATE_KEY"))
        client = HpsiMcpClient(api_key="hpsi_test_key")
        self.assertIsNone(client._wallet)
        client.close()

    def test_a_wallet_needs_a_key(self) -> None:
        from hpsilab_mcp import X402Wallet

        with self.assertRaises(ValueError):
            X402Wallet("")

    def test_wallet_repr_does_not_expose_its_address(self) -> None:
        from hpsilab_mcp import X402Wallet

        wallet = X402Wallet.__new__(X402Wallet)
        wallet.address = "0x1111111111111111111111111111111111111111"
        wallet.max_price_usdc = 1.0

        rendered = repr(wallet)
        self.assertNotIn("111111", rendered)
        self.assertIn("[REDACTED]", rendered)


if __name__ == "__main__":
    unittest.main()
