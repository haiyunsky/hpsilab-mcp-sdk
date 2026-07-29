"""402 handling: what the client does when a call has to be paid for.

The signing itself belongs to the x402 library and needs a funded key, so the
wallet is stubbed here — these tests cover the client's part of the contract:
pay only when asked, retry exactly once, and otherwise hand the caller a
challenge they can act on.
"""

import unittest

import httpx

from hpsilab_mcp import HpsiMcpClient
from hpsilab_mcp.errors import HpsiMcpPaymentError

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
    def test_402_without_a_wallet_raises_with_the_challenge_attached(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=CHALLENGE)

        client = HpsiMcpClient(transport=httpx.MockTransport(handler))

        with self.assertRaises(HpsiMcpPaymentError) as caught:
            client.get_monte_carlo("NVDA")

        error = caught.exception
        self.assertEqual(error.status_code, 402)
        self.assertEqual(error.tool, "get_monte_carlo")
        self.assertEqual(error.price, "$0.10")
        self.assertEqual(error.accepts[0]["network"], "eip155:8453")
        # The message should tell a human how to make it work, not just restate
        # that they were refused.
        self.assertIn("$0.10", str(error))
        self.assertIn("X402Wallet", str(error))
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

        with self.assertRaises(HpsiMcpPaymentError):
            client.get_monte_carlo("NVDA")

        self.assertEqual(wallet.calls, 1)
        client.close()

    def test_a_refused_challenge_propagates_untouched(self) -> None:
        # e.g. the price is over max_price_usdc, or the network has no scheme.
        # The wallet's own error is the useful one; don't bury it under a
        # generic payment error.
        wallet = _StubWallet(error=ValueError("amount exceeds max_amount policy"))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json=CHALLENGE)

        client = HpsiMcpClient(transport=httpx.MockTransport(handler), wallet=wallet)

        with self.assertRaises(ValueError):
            client.get_monte_carlo("NVDA")
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
        client = HpsiMcpClient()
        self.assertIsNone(client._wallet)
        client.close()

    def test_a_wallet_needs_a_key(self) -> None:
        from hpsilab_mcp import X402Wallet

        with self.assertRaises(ValueError):
            X402Wallet("")


if __name__ == "__main__":
    unittest.main()
