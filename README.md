# HPSILab Python REST SDK

`hpsilab-mcp` is the official Python SDK for the hosted hpsilab.com REST API — quantitative finance and options analytics (IV surface, Monte Carlo simulation, AI predictions, pre-trade risk scans, and more).

> **Note:** This package wraps REST endpoints only. It does not implement MCP transport — see [MCP Transport](#mcp-transport) below if you need that.

## Requirements

- Python >= 3.9

## Installation

```bash
pip install hpsilab-mcp
```

To let the client pay per call instead of registering an account (see
[Paying without an account](#paying-without-an-account)):

```bash
pip install "hpsilab-mcp[x402]"
```

## Getting an API Key

`HpsiMcpClient()` requires a real `api_key` (or a `wallet=` — see [Paying
without an account](#paying-without-an-account)). Two ways to get a key:

- **From the website**: sign up at <https://hpsilab.com/register>, then
  **Settings → API Keys**.
- **From code** (no browser, for agents):

  ```python
  import hpsilab_mcp
  api_key = hpsilab_mcp.register(email="you@example.com")["api_key"]
  ```

Either way you end up with a real `hpsi_` key — pass it as `api_key=`. See
[Registering your own account](#registering-your-own-account-for-agents) for
details (email verification, lost-key recovery, idempotent re-calls).

## Quick Start

Path B end-to-end — register, then call a tool:

```python
import hpsilab_mcp
from hpsilab_mcp import HpsiMcpClient

result = hpsilab_mcp.register(email="you@example.com")
client = HpsiMcpClient(api_key=result["api_key"])

calls = {
    "analyze_stock": client.analyze_stock("NVDA"),
    "get_ai_prediction": client.get_ai_prediction("NVDA"),
    "get_iv_radar": client.get_iv_radar("NVDA"),
    "get_option_pressure": client.get_option_pressure("NVDA"),
    "get_pretrade_risk_scan": client.get_pretrade_risk_scan("NVDA"),
    "get_monte_carlo": client.get_monte_carlo("NVDA"),
    "get_equity_curve": client.get_equity_curve("NVDA"),
    "generate_stock_images": client.generate_stock_images("NVDA"),
    "generate_stock_research_report": client.generate_stock_research_report("NVDA"),
}

print(calls["analyze_stock"])
```

## Authentication

Every REST SDK method requires either a real account (`api_key=`) or a
configured x402 `wallet=` (see [Paying without an
account](#paying-without-an-account) below) — the SDK enforces this at
construction time, before any request goes out, rather than letting an
unauthenticated call reach the API and fail there.

```python
from hpsilab_mcp import HpsiMcpClient

client = HpsiMcpClient(
    api_key="YOUR_API_KEY",
    base_url="https://hpsilab.com",
)

result = client.get_ai_prediction("TSLA")
print(result)
```

### Credits

Usage is metered in **Credits**, not requests. One Credit is one unit of fresh
compute; reading a cached or public result costs nothing, and a call that fails
is never charged.

| Plan | Price | Included |
| --- | --- | --- |
| Developer | $19/month | 2,000 Credits/month |
| Pro | $99/month | 15,000 Credits/month |
| Enterprise | From $2,000/month | Custom limits |
| Anonymous Trial | — | 36 Credits / 72 hours |
| Registered Trial | — | 100 Credits / 14 days |

Every response carries what it cost:

```
X-Credits-Charged:   5
X-Credits-Remaining: 1995
```

Per-tool prices are served live at `GET /api/credits/catalog`, and the current
balance at `GET /api/credits/balance` — both free to call.

Running out raises its own error, deliberately **not** a rate-limit error:
waiting fixes a rate limit and never refills a balance.

```python
from hpsilab_mcp import HpsiMcpInsufficientCreditsError

try:
    client.get_monte_carlo("NVDA")
except HpsiMcpInsufficientCreditsError as exc:
    print(exc.credits_required, exc.credits_remaining)  # 30 12
    print(exc.upgrade_url)                              # where to add Credits
```

Credits and rate limits are separate meters: Credits decide *whether* you may
spend compute, RPM and concurrency decide *how fast*. A Credits refusal is an
HTTP 403 with `error: "insufficient_credits"`, never a 429.

### Authentication failures and rate limits

A `429` (rate limit / quota exceeded) raises `HpsiMcpRateLimitError` with the
backend's fields promoted onto it — no need to parse `response_text` yourself:

```python
from hpsilab_mcp import HpsiMcpRateLimitError

try:
    client.get_ai_prediction("NVDA")
except HpsiMcpRateLimitError as exc:
    print(exc.tool, exc.limit, exc.window)     # get_ai_prediction 30 day
    print(exc.register_url, exc.pricing_url)   # where to register / upgrade
    print(exc.body)                            # the full raw response, if needed
```

An unresolved `401` raises `HpsiMcpConfigError` and opens an authentication
circuit breaker on that Client. Later calls fail locally without another HTTP
request. Recover with `client.set_api_key(...)`, `client.set_wallet(...)`, or
a new Client. A `403` remains `HpsiMcpAuthError`; a `429` remains
`HpsiMcpRateLimitError` and neither opens this circuit.

## Registering your own account (for agents)

No client instance needed — this is the entry point for a caller that has
neither an `api_key` nor a wallet yet. No password, no web form:

```python
import hpsilab_mcp
from hpsilab_mcp import HpsiMcpClient

result = hpsilab_mcp.register(email="you@example.com")
client = HpsiMcpClient(api_key=result["api_key"])
client.get_monte_carlo("NVDA")     # now metered as your account
```

The account is *also* bound to this caller server-side — so a process that
cannot change its own `Authorization` header (an MCP connection, for
instance) is still recognised on later calls made from the same caller.

The account starts unverified, which keeps the anon-rate daily allowance
until the emailed link is confirmed; confirming it unlocks the full Free
plan. Use a real address — one nobody reads leaves the account at that lower
allowance forever.

Calling `hpsilab_mcp.register()` again with the same email returns the same
account and a fresh key rather than creating a second one, so it is safe to
call when you have lost your key. An address that already belongs to a
different account raises `HpsiMcpAPIError` with status `409`.

Already have a client constructed (typically wallet-only, via `wallet=`) and
want it to also have an account? `HpsiMcpClient.register_account(email)` is
the same registration, as an instance method — it switches the client over to
the new key automatically. Pass `adopt_key=False` to get the response without
switching, e.g. to hand the key to another process instead.

### Lost the verification email?

An unverified account stays on the anon-rate daily allowance — not the full
Free plan — until the link in that email is confirmed. If the email never
arrived or the link expired, request a new one instead of registering again:

```python
client.resend_verification_email()
```

Requires a real account key (`api_key=`, or whatever `register_account()`
just adopted) — a wallet-only client, or one with an invalid/expired key, gets
`HpsiMcpConfigError` and opens the local authentication circuit: there's no
more fingerprint-based fallback for a
header-less caller (API key is mandatory now, and fingerprint binding was
itself a no-key-needed identity — closed along with the rest of anonymous
access). The backend also enforces a short cooldown between resends; calling
it again too soon raises `HpsiMcpRateLimitError`.

## Paying without an account

Calling a tool with no `api_key` — a `wallet=` alone is enough to construct a
client — the API answers **HTTP 402** with an [x402](https://x402.org)
payment challenge instead of refusing outright, so an agent can pay for the
call in USDC on Base and keep working without ever registering.

**You do not need a wallet either**, if you'd rather register instead — see
[Registering your own account](#registering-your-own-account-for-agents)
above; it needs no wallet and no browser, and resolves this within the
running process. Every 402 challenge also names a card checkout URL
(`https://hpsilab.com/pricing?anon=...`) for a human to pay with a card
instead, if neither a wallet nor unattended registration fits.

Without a wallet the SDK does not retry a `402`. It raises
`HpsiMcpPaymentError`, carrying the challenge so you can settle it with your
own x402 client if you'd rather:

```python
from hpsilab_mcp import HpsiMcpPaymentError

try:
    client.get_monte_carlo("NVDA")
except HpsiMcpPaymentError as exc:
    print(exc.price, exc.accepts)
```

The rest of the client keeps working — one tool being priced says nothing
about the next one.

With a wallet, the client signs the challenge and repeats the request for you:

```python
from hpsilab_mcp import HpsiMcpClient, X402Wallet

client = HpsiMcpClient(wallet=X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
client.get_monte_carlo("NVDA")   # no account needed — paid per call
```

### Holding a wallet is not the same as agreeing to spend it

Payment is governed by a `PaymentPolicy`, separately from whether a wallet
exists. The default mode is **`credits_only`**: the SDK never pays.

```python
from hpsilab_mcp import HpsiMcpClient, PaymentPolicy, X402Wallet

client = HpsiMcpClient(
    wallet=X402Wallet(PRIVATE_KEY),    # no api_key — see the note below
    payment_policy=PaymentPolicy(
        mode="x402_fallback",          # the opt-in; default "credits_only"
        max_payment_per_call="0.20",
        max_payment_per_session="2.00",
        max_payment_per_day="10.00",
        allowed_payment_assets={"USDC"},
        allowed_networks={"base"},
        x402_allowed_tools={"get_monte_carlo", "get_pretrade_risk_scan"},
    ),
)

client.payment_spend_summary()   # what's been spent, and against which ceilings
```

> **A wallet does not top up an account.** Adding `api_key=` to the client
> above does not give it a pay-per-call fallback for when Credits run out —
> the wallet would simply never be used. The API does not offer x402 to a
> caller it can identify: a signed-in request that exceeds its plan gets
> `402 insufficient_credits`, which carries no payment offer at all, so
> `PaymentPolicy` has nothing to authorise and the SDK raises
> `HpsiMcpInsufficientCreditsError`. Buying Credits and paying per call are
> two separate doors, and holding a key means you are already through the
> first one.
>
> So a wallet is worth configuring in exactly one situation: a client with
> **no** `api_key`, paying its own way without an account. If you have a key
> and run out of Credits, the way forward is
> [upgrading](https://hpsilab.com/pricing), not a wallet.

`payment_mode="x402_fallback"` is shorthand when the default ceilings suit you.

When `payment_mode` is not given, it is derived:

| Wallet came from | `api_key` | Mode |
| --- | --- | --- |
| `wallet=` in the constructor | absent | `x402_fallback` |
| `wallet=` in the constructor | present | `x402_fallback`, but see the note above — nothing ever offers this client a payment |
| `HPSILAB_X402_PRIVATE_KEY` | absent | `x402_fallback` |
| `HPSILAB_X402_PRIVATE_KEY` | present | `credits_only` |

The last row is the one that changed in 0.13: a private key left in the
environment by another project is not consent to spend it, and a keyed client
that finds one goes on paying with Credits. Pass `payment_mode` explicitly if
you want the old behaviour.

Regardless of configuration:

* Nothing is paid pre-emptively — the call is always attempted first, and only
  pays if the response comes back 402 **carrying an offer**. An ordinary "out
  of Credits" 402 has no `accepts` and is never payable in either mode.
* Each call signs **once**. A server that answers 402 even after payment
  closes the x402 path for that client, so it cannot drain the wallet one call
  at a time; Credits-funded calls keep working.
* An offer in an asset the SDK cannot price is refused rather than signed. The
  amount is an integer in that asset's base units, so misreading the decimals
  is not a rounding error.
* A payment whose outcome is unknown — the retry timed out or the connection
  dropped — is counted as spent and closes the x402 path, rather than being
  re-attempted.
* Budgets are not refunded, and replacing the policy does not reset them.

Signing happens locally; the private key never leaves your process.

To recover an existing Client after a `401` or unresolved `402`:

```python
client.set_api_key("NEW_API_KEY")
# or
client.set_wallet(X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
```

See [Upgrading](docs/upgrading.md) for the exception-contract migration.

Pay-per-call is an allowlist. A tool that is not on it answers `401`/`402`
without an offer, and the way through is an API key or OAuth — not a wallet.

| Tool | Price per call | Payable with a wallet |
| --- | ---: | --- |
| `get_pretrade_risk_scan` | $0.15 | yes |
| `get_monte_carlo` | $0.10 | yes |
| `get_equity_curve` | $0.07 | yes |
| `get_iv_radar`, `get_option_pressure`, `get_ai_prediction` | $0.05 | yes |
| `analyze_stock` | $0.15 | no |
| `generate_stock_research_report` | $0.35 | no |

Nothing in the SDK needs configuring for this — a tool that cannot be bought
simply never produces a settleable offer, so `PaymentPolicy` never authorises a
payment for it and `HpsiMcpPaymentError` explains that no offer arrived.

## Version

```python
import hpsilab_mcp

print(hpsilab_mcp.__version__)
```

## Request tracking

Every request carries `X-HPSILAB-Source: sdk`, `X-HPSILAB-Client: python-sdk`,
`X-HPSILAB-Version: <installed version>`, `X-HPSILAB-Tool: <method name>` (e.g.
`get_ai_prediction`), and `User-Agent: hpsilab-python-sdk/<version>`. These are
merged into any custom `headers` you pass to `HpsiMcpClient(...)` without
overriding `Authorization` or other business headers.

## REST SDK Methods

| Method | Endpoint |
| --- | --- |
| `analyze_stock(symbol)` | `GET /api/analyze_stock/{symbol}` |
| `get_ai_prediction(symbol)` | `GET /api/ai_prediction/{symbol}` |
| `get_iv_radar(symbol)` | `GET /api/iv_batch?symbols={symbol}` |
| `get_option_pressure(symbol)` | `GET /api/option_pressure/{symbol}` |
| `get_pretrade_risk_scan(symbol)` | `GET /api/pretrade-risk-scan?symbol={symbol}` |
| `get_monte_carlo(symbol)` | `GET /api/monte_carlo/{symbol}` |
| `get_equity_curve(symbol)` | `GET /api/equity_curve/{symbol}` |
| `get_equity_curves(symbol)` | Deprecated alias of `get_equity_curve` — warns on use |
| `generate_stock_images(symbol)` | `POST /api/stock_report/{symbol}/images` |
| `generate_stock_research_report(symbol)` | `POST /api/stock_report/{symbol}/research_report` |

The SDK itself does not publish MCP tool annotations; those are declared by the
MCP server in its `tools/list` response. The `GET` analysis methods are
read-only. The two `generate_*` methods create or refresh hosted artifacts and
may consume quota or trigger payment; repeated calls are not guaranteed to be
idempotent.

## Capability Matrix

| Capability | REST API | MCP |
| --- | --- | --- |
| `analyze_stock` | Yes | Yes |
| `get_ai_prediction` | Yes | Yes |
| `get_iv_radar` | Yes | Yes |
| `get_option_pressure` | Yes | Yes |
| `get_pretrade_risk_scan` | Yes | Yes |
| `get_monte_carlo` | Yes | Yes |
| `get_equity_curve` | Yes | Yes |
| `generate_stock_images` | Yes | Yes |
| `generate_stock_research_report` | Yes | Yes |

## MCP Transport

All official MCP tools have REST SDK coverage. Use an MCP-compatible client (e.g. Claude, or any MCP host) when you specifically need MCP transport, tool discovery, or assistant-native tool calls — see the [MCP server docs](https://hpsilab.com/developer/v2) for setup.

## Scope

This package is a REST API wrapper only. It does not implement MCP transport, SSE, streaming, tool discovery, Claude integration, or proprietary finance logic.

These tools return research-oriented information. **They are not financial advice.**

## Links

- [Homepage](https://hpsilab.com)
- [Developer Portal](https://hpsilab.com/developer/v2)
- [Repository](https://github.com/haiyunsky/hpsilab-mcp-sdk)

## License

MIT. See `LICENSE`.
