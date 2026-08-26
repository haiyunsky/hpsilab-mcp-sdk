# HPSILab Python REST SDK

`hpsilab-mcp` is the official Python SDK for the hosted hpsilab.com REST API — quantitative finance and options analytics (IV surface, Monte Carlo simulation, AI predictions, pre-trade risk scans, and more).

> **Note:** This package wraps REST endpoints and can decode results supplied
> by an MCP transport adapter. It does not implement MCP transport itself — see
> [MCP Transport](#mcp-transport) below.

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

## Get an API Key

Get a free API key before calling the SDK:

1. Register at **<https://hpsilab.com/register>**.
2. Open **Settings → API Keys** and copy your `hpsi_...` key.

Keep the API key private. Replace `YOUR_API_KEY` below with the complete
`hpsi_...` value:

```python
from hpsilab_mcp import HpsiMcpClient

try:
    client = HpsiMcpClient(api_key="hpsi_your_api_key_here")
    print(client.analyze_stock("NVDA"))
except Exception as e:
    print(f"HPSILab error: {e}")
```

Pass only the key value. Do not add a `Bearer ` prefix—the SDK adds the
`Authorization: Bearer <API_KEY>` header automatically.

## Quick Start

Use the API key from the previous section. Replace `YOUR_API_KEY` with your
actual `hpsi_...` key:

```python
from hpsilab_mcp import HpsiMcpClient, HpsiMcpError

try:
    client = HpsiMcpClient(
        api_key="YOUR_API_KEY",
        base_url="https://hpsilab.com",
    )
    result = client.get_ai_prediction("TSLA")
    print(result)
except HpsiMcpError as exc:
    print(f"Prediction request failed: {exc}")
```

Complete account verification when prompted to unlock the full Free plan.

### Anonymous Trial

For evaluation, `HpsiMcpClient()` can start without a key and receives the
one-time **36 Credits / 72 hours** Anonymous Trial. Persist
`client.anonymous_credential` if a later process must reuse that balance.

## Authentication

SDK calls resolve identity in this order: a real account `api_key=` first, then
a restored SDK `anonymous_credential=`, otherwise a new tokenless SDK Anonymous
Trial. An invalid credential fails with 401 and never falls back to anonymous.
A configured x402 `wallet=` remains available under its existing payment policy
after Credits cannot fund a call; successful x402 settlement is not also charged
to Credits.

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

Credits and rate limits are separate meters: Credits decide *whether* you may
spend compute, RPM and concurrency decide *how fast*. A Credits refusal is an
HTTP 402 with `error: "insufficient_credits"`, never a 429. After the first
refusal, the client blocks concurrent and subsequent calls locally for 60
seconds. Call `client.clear_insufficient_credits_circuit()` after adding
Credits to recheck immediately.

### Errors and rate limits

Catch `HpsiMcpError` when an application needs one common SDK error boundary.
More specific subclasses include `HpsiMcpConfigError` for authentication,
`HpsiMcpInsufficientCreditsError` for an empty balance, and
`HpsiMcpRateLimitError` for HTTP 429 responses. Exception objects retain the
safe structured response fields; normal applications do not need to parse the
raw response body.

Anonymous clients are shown only the registration route. Clients using an API
key are shown only the paid upgrade route when the backend makes one available.
The SDK validates registration, pricing, and upgrade URLs before including them
in an exception.

An unresolved `401` raises `HpsiMcpConfigError` and opens an authentication
circuit breaker on that Client. Later calls fail locally without another HTTP
request. Recover with `client.set_api_key(...)`, `client.set_wallet(...)`, or
a new Client. A `403` remains `HpsiMcpAuthError`; a `429` remains
`HpsiMcpRateLimitError` and neither opens this circuit.

## Managing Your API Key

Create an account at <https://hpsilab.com/register>, then create or copy an API
key from **Settings → API Keys**. Pass that key to `HpsiMcpClient(api_key=...)`.

The account is *also* bound to this caller server-side — so a process that
cannot change its own `Authorization` header (an MCP connection, for
instance) is still recognised on later calls made from the same caller.

The account starts unverified, which keeps the anon-rate daily allowance
until the emailed link is confirmed; confirming it unlocks the full Free
plan. Use a real address — one nobody reads leaves the account at that lower
allowance forever.

If a key is lost or rotated, create a replacement from Settings and update the
client with `client.set_api_key("NEW_API_KEY")`.

### Lost the verification email?

An unverified account stays on the anon-rate daily allowance — not the full
Free plan — until the link in that email is confirmed. If the email never
arrived or the link expired, request a new one instead of registering again:

Call `client.resend_verification_email()` with a valid account API key to send
a new verification message.

Requires a real account key passed with `api_key=`. A wallet-only client, or
one with an invalid/expired key, gets
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

**You do not need a wallet either**, if you'd rather create an account and API
key instead—see [Get an API Key](#get-an-api-key) above. Every 402 challenge
also names a card checkout URL
(`https://hpsilab.com/pricing?anon=...`) for a human to pay with a card
instead, if neither a wallet nor unattended registration fits.

Without a wallet the SDK does not retry a `402`. It raises
`HpsiMcpPaymentError`, carrying the challenge so an application can inspect or
settle it with its own x402 client.

Known facilitator rejections retain their safe protocol meaning. An empty
wallet reports `Payment rejected: insufficient_funds.` An `invalid_payload`
reports that the signed payload could not be validated and that wallet balance
was not confirmed; it does not incorrectly claim insufficient funds. Complete
response context remains available through recursively redacted exception
fields such as `body`, while raw facilitator diagnostics are not copied into
`str(exc)`. Registration and plan choices remain separate account flows
because the exception itself does not know which conversion route is
appropriate for the caller.

The rest of the client keeps working — one tool being priced says nothing
about the next one.

With a wallet, the client signs the challenge and repeats the request for you:

```python
from hpsilab_mcp import HpsiMcpClient, X402Wallet

try:
    client = HpsiMcpClient(wallet=X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
    print(client.get_monte_carlo("NVDA"))  # no account needed — paid per call
except Exception as e:
    print(f"HPSILab error: {e}")
```

### Holding a wallet is not the same as agreeing to spend it

Payment is governed by a `PaymentPolicy`, separately from whether a wallet
exists. The default mode is **`credits_only`**: the SDK never pays.

```python
from hpsilab_mcp import HpsiMcpClient, PaymentPolicy, X402Wallet

try:
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
    print(client.payment_spend_summary())
except Exception as e:
    print(f"HPSILab error: {e}")
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
* When a challenge lists several offers, **the cheapest acceptable one is
  taken**, not the first. A ceiling bounds the worst price and says nothing
  about the gap to the best one, so choosing by list order would let whoever
  writes the challenge decide how much of your allowance to consume simply by
  ordering it.
* **What the wallet signs is checked against what the policy approved** —
  amount, asset and network — before the payment leaves the process. The
  policy picks an offer and the wallet picks one independently; a multi-offer
  challenge could otherwise be approved at one price and signed at another. A
  mismatch closes the x402 path and charges nothing.
* A payment whose outcome is unknown — the retry timed out, the connection
  dropped, or the API answered `settlement_status: "unknown"` — is counted as
  spent and closes the x402 path, rather than being re-attempted. See
  [Unresolved settlements](#unresolved-settlements) below.
* Every request carries an `X-Request-Id`, one per logical call and shared by
  the unpaid attempt and the paid retry. The API's settlement ledger is unique
  on it, so one call cannot be settled by two different transactions.
* Budgets are not refunded, and replacing the policy does not reset them.

Signing happens locally; the private key never leaves your process.

### Unresolved settlements

A payment can leave this process and never come back with an answer — the
facilitator timed out, or the API could not confirm what happened to it. The
money may have moved. **Paying again is the one thing that must not happen**,
because a second attempt signs a new authorization and buys the same call
twice.

The SDK raises `HpsiMcpSettlementUnknownError` for this. It is deliberately not
a subclass of `HpsiMcpAPIError`, preventing a broad API-error retry handler
from buying the same call twice.

The exception carries `call_id`, `tool` and `settlement_status`. **Keep the
`call_id`**: it is what reconciliation needs to decide whether the money moved,
and the API's ledger records the same id.

Afterwards the client stops paying, and says so:

```python
try:
    print(client.payment_spend_summary())
except Exception as e:
    print(f"HPSILab error: {e}")
```

Credits-funded calls keep working — nothing about the API key failed. Once
reconciliation has said what happened, `client.set_wallet(wallet)` reopens the
x402 path; the `unresolved_settlements` record is kept, because a caller
resuming payments still needs the evidence.

To recover an existing Client after a `401` or unresolved `402`:

```python
try:
    client.set_api_key("NEW_API_KEY")
    # or: client.set_wallet(X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
except Exception as e:
    print(f"HPSILab error: {e}")
```

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

Current release: **0.13.15**

```python
import hpsilab_mcp

try:
    print(hpsilab_mcp.__version__)
except Exception as e:
    print(f"HPSILab error: {e}")
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

All official MCP tools have REST SDK coverage. Applications that already have
a configured synchronous MCP transport can pass a
`call_tool(name, arguments)` callback through `mcp_transport`.

With `include_metadata=False` (the default), `call_tool` returns the transport
adapter's original value unchanged. With it enabled, `result.metadata` is a
read-only view of the MCP result's `_meta` and exposes `result_id`,
`source_ids`, `upstream_ids`, `derived_from`, and `timestamp`. The SDK never
generates or infers these identifiers. Missing metadata returns `None`; missing
individual list fields return an empty list. The complete unmodified mapping
is available as `result.metadata.raw`.

The callback must return the raw `CallToolResult` or its decoded JSON form.
Transport setup, sessions, streaming, and tool discovery remain the
responsibility of the MCP client library. See the
[MCP server docs](https://hpsilab.com/developer/v2) for connection setup.

## Scope

This package provides REST methods plus an adapter for decoded MCP tool
results. It does not itself implement MCP transport, SSE, streaming, tool
discovery, Claude integration, or proprietary finance logic.

These tools return research-oriented information. **They are not financial advice.**

## Links

- [Homepage](https://hpsilab.com)
- [Developer Portal](https://hpsilab.com/developer/v2)
- [Repository](https://github.com/haiyunsky/hpsilab-mcp-sdk)

## License

MIT. See `LICENSE`.
