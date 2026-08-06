"""Optional x402 pay-per-call support.

The API answers HTTP 402 when an anonymous caller has used up a tool's free
quota, or asks for a Pro tool. A 402 is not a dead end: it carries an x402
challenge, and a caller holding a funded wallet can sign it and repeat the
request to get the data now instead of waiting for the quota to reset.

This module is the wallet half of that. It is an *optional* dependency —
``pip install "hpsilab-mcp[x402]"`` — and nothing here is imported unless a
wallet is actually configured, so the SDK keeps working with no crypto stack
installed at all.

    from hpsilab_mcp import HpsiMcpClient, X402Wallet

    client = HpsiMcpClient(wallet=X402Wallet(private_key, max_price_usdc=0.20))
    client.get_monte_carlo("NVDA")   # pays only if the API asks it to

Nothing is ever paid pre-emptively: the client makes the ordinary free call
first and only signs if the API comes back 402. Payments are capped per call
by ``max_price_usdc`` (default $1.00) — a challenge asking for more is
refused rather than signed.
"""

from __future__ import annotations

import os
from typing import Any, Optional

# hpsilab prices in USDC, which has 6 decimals; x402's amount fields and its
# max_amount policy are both in those base units.
_USDC_DECIMALS = 6

ENV_PRIVATE_KEY = "HPSILAB_X402_PRIVATE_KEY"

_INSTALL_HINT = (
    "x402 payment support requires the optional extra: "
    'pip install "hpsilab-mcp[x402]"'
)


class X402Wallet:
    """Signs x402 payment challenges with an EVM private key.

    Args:
        private_key: EVM private key (``0x``-prefixed hex) for the paying
            account. Read from the ``HPSILAB_X402_PRIVATE_KEY`` environment
            variable when omitted.
        max_price_usdc: Per-call ceiling. A challenge asking for more than this
            is left unpaid and surfaces as ``HpsiMcpPaymentError``. Pass None to
            remove the cap — only sensible if you trust the endpoint completely.

    The key never leaves this process: it signs a payment authorization locally
    and only the signature travels with the retry.
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        *,
        max_price_usdc: Optional[float] = 1.0,
        networks: Optional[list] = None,
    ) -> None:
        key = (private_key or os.environ.get(ENV_PRIVATE_KEY) or "").strip()
        if not key:
            raise ValueError(
                f"An EVM private key is required — pass private_key= or set {ENV_PRIVATE_KEY}."
            )

        try:
            from eth_account import Account
            from x402 import max_amount, x402ClientSync
            from x402.http import x402HTTPClientSync
            from x402.mechanisms.evm.exact import register_exact_evm_client
        except ImportError as exc:  # pragma: no cover - depends on the install
            # Keep the underlying reason in the message. A partial install —
            # x402 present but its EVM signer deps missing — otherwise reports
            # "install the extra" to someone who already did, which is what
            # made 0.6.0's bad extra hard to read.
            raise ImportError(f"{_INSTALL_HINT} (underlying import error: {exc})") from exc

        try:
            account = Account.from_key(key)
        except Exception:
            # Third-party parsers may retain or echo their input on failure.
            # Replace the exception and chain before it reaches logs or APM.
            raise ValueError("The configured EVM private key is invalid.") from None
        finally:
            key = ""
        self.address: str = account.address
        self.max_price_usdc = max_price_usdc

        policies = None
        if max_price_usdc is not None:
            policies = [max_amount(int(round(max_price_usdc * 10**_USDC_DECIMALS)))]

        client = x402ClientSync()
        register_exact_evm_client(client, account, networks=networks, policies=policies)
        self._http = x402HTTPClientSync(client)

    def payment_headers(self, response: Any) -> dict:
        """Turn a 402 response into the headers that pay for the retry.

        Reads the challenge from wherever the server put it (the
        ``PAYMENT-REQUIRED`` header or the JSON body) and returns the single
        payment header the retry needs. Raises if the challenge is unreadable,
        asks for more than ``max_price_usdc``, or names a network/asset this
        wallet has no scheme for — never returns unsigned/partial headers.
        """
        headers, _payload = self._http.handle_402_response(
            dict(response.headers), response.content
        )
        return dict(headers or {})

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        cap = "uncapped" if self.max_price_usdc is None else f"max ${self.max_price_usdc:g}/call"
        return f"<X402Wallet address=[REDACTED] {cap}>"


def wallet_from_env() -> Optional[X402Wallet]:
    """Build a wallet from ``HPSILAB_X402_PRIVATE_KEY``, or None if unset.

    Returns None rather than raising when the extra isn't installed: an
    environment variable left over from another project must not stop the SDK
    from making ordinary free calls.
    """
    if not (os.environ.get(ENV_PRIVATE_KEY) or "").strip():
        return None
    try:
        return X402Wallet()
    except ImportError:
        return None
