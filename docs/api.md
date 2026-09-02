# Python REST SDK API

The `hpsilab-mcp` package provides a lightweight synchronous REST API wrapper
for the hosted hpsilab.com REST API.

The Python SDK currently wraps hosted REST endpoints for the official tool catalog.

Hosted base URL:

```text
https://hpsilab.com
```

## Installation

```bash
pip install hpsilab-mcp
```

## Client

```python
from hpsilab_mcp import HpsiMcpClient

client = HpsiMcpClient()
```

The first eligible call without credentials starts the SDK channel's one-time
36 Credits / 72 hours Anonymous Trial. The SDK does not block tool methods
client-side.

Optional API key support is available when you want to send an Authorization
header:

```python
client = HpsiMcpClient(api_key="YOUR_API_KEY")
```

Do not commit API keys or local secrets.

### Anonymous credential (automatic)

You do not need to do anything to get one. On your first successful call the
API issues an `hpsi_anon_*` credential and the client adopts it automatically.
Every later request on that client uses the same Anonymous Billing Owner and
balance:

```python
client = HpsiMcpClient()
client.get_monte_carlo("NVDA")
client.anonymous_credential   # 'hpsi_anon_...' — issued and now in use
```

`anonymous_credential` is `None` until one has been issued, and stays `None`
for a client built with `api_key=` — a real account credential always takes
priority and is never displaced.

To keep the larger allowance across processes, persist `client.anon_key` and
pass it back in:

```python
client = HpsiMcpClient(anonymous_credential=saved_credential)
```

Persist the credential if the Anonymous Trial balance must survive a new
client or process. Invalid credentials fail with HTTP 401 and never fall back
to a fresh anonymous identity.

Binding an email to the key unlocks the full Free plan:
<https://hpsilab.com/register>

### Self-registration (for agents)

`register_account(email, adopt_key=True)` completes the anonymous → account
transition with no human step and no web form:

```python
client = HpsiMcpClient()
client.register_account("you@example.com")
client.get_monte_carlo("NVDA")   # metered as your account
```

The client adopts the returned account key (`anonymous_credential` becomes
`None`, since no anonymous identity is in play any more).

The account is created **unverified**, which resolves to the anonymous quota
row until the emailed link is confirmed; confirming it lifts the caller to the
real Free plan. Use an address a human actually reads.

Idempotent per caller: a repeat call returns the same account with a fresh key
(the old one keeps working) rather than creating a second. An address that
already belongs to a different account raises `HpsiMcpAPIError` with
`status_code == 409` and leaves the client's current identity untouched.

Pass `adopt_key=False` to receive the payload without switching this client
over — e.g. to hand the key to another process.

| Method | Endpoint |
| --- | --- |
| `register_account(email)` | `POST /api/agent/register` |

### Wallet (optional)

`wallet=` lets the client answer an HTTP 402 payment challenge instead of
raising it (see [Payments](#payments)):

```python
from hpsilab_mcp import HpsiMcpClient, X402Wallet

client = HpsiMcpClient(wallet=X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
```

Requires `pip install "hpsilab-mcp[x402]"`. Omit `private_key` to read
`HPSILAB_X402_PRIVATE_KEY`; a client built with no `wallet=` picks that same
variable up automatically. Do not commit private keys.

## Methods

```python
client.analyze_stock("NVDA")
client.get_ai_prediction("NVDA")
client.get_iv_radar("NVDA")
client.get_option_pressure("SPY")
client.get_pretrade_risk_scan("NVDA")
client.get_monte_carlo("QBTS")
client.get_equity_curve("IONQ")
client.generate_stock_images("NVDA")
client.generate_stock_research_report("NVDA")
```

Endpoint mapping:

| Method | Endpoint |
| --- | --- |
| `analyze_stock(symbol)` | `GET /api/analyze_stock/{symbol}` |
| `get_ai_prediction(symbol)` | `GET /api/ai_prediction/{symbol}` |
| `get_iv_radar(symbol)` | `GET /api/iv_batch?symbols={symbol}` |
| `get_option_pressure(symbol)` | `GET /api/option_pressure/{symbol}` |
| `get_pretrade_risk_scan(symbol)` | `GET /api/pretrade-risk-scan?symbol={symbol}` |
| `get_monte_carlo(symbol)` | `GET /api/monte_carlo/{symbol}` |
| `get_equity_curve(symbol)` | `GET /api/equity_curve/{symbol}` |
| `generate_stock_images(symbol)` | `POST /api/stock_report/{symbol}/images` |
| `generate_stock_research_report(symbol)` | `POST /api/stock_report/{symbol}/research_report` |

MCP behavior annotations belong to the MCP server and are not emitted by this
REST SDK. The `GET` methods are read-only. The two `generate_*` methods create
or refresh hosted artifacts and may consume quota or trigger payment; callers
should not assume repeated requests are idempotent.

`get_equity_curves(symbol)` is a deprecated alias of `get_equity_curve(symbol)`;
it warns on use and will be removed in the next major release.

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
| `register_account` | Yes | Yes (`register_account` tool) |

## MCP Transport

All official MCP tools now have REST SDK coverage. Use an MCP-compatible client
when you specifically need MCP transport, tool discovery, or assistant-native
tool calls.

### SDK dependency metadata

`call_tool(..., include_metadata=True)` returns
`McpToolResult(data=..., metadata=...)`. The SDK generates `result_id`,
`source_ids`, `upstream_ids`, `derived_from`, and `timestamp` locally; it never
requires metadata from no external component. The default call remains
unchanged.

### Tool execution errors

MCP reports a tool that ran and failed inside an otherwise ordinary result: the
error text sits in `content` with `isError` set beside it, so the failure is
shaped exactly like a success. `call_tool` reads the flag and raises
`HpsiMcpToolError` on both paths — returning the result would hand back the
failure text as business data, and `include_metadata=True` would additionally
generate a dependency record for a call that produced no output.

A call the server could not route at all is a JSON-RPC protocol error and never
reaches this SDK; that belongs to the transport adapter.

## Errors

The SDK exposes typed exceptions:

* `HpsiMcpError`
* `HpsiMcpConfigError`
* `HpsiMcpConnectionError`
* `HpsiMcpTimeoutError`
* `HpsiMcpAPIError`
* `HpsiMcpAuthError`
* `HpsiMcpPaymentError`
* `HpsiMcpInsufficientCreditsError`
* `HpsiMcpAllowanceExhaustedError`
* `HpsiMcpRateLimitError`
* `HpsiMcpResponseError`
* `HpsiMcpSettlementUnknownError`
* `HpsiMcpToolError`

`HpsiMcpPaymentError` preserves safe facilitator reasons. An empty wallet is
reported as `Payment rejected: insufficient_funds.` For `invalid_payload`, the
message states that the signed payload could not be validated and wallet
balance was not confirmed; it does not guess that funds are insufficient.
Payment-aware callers should inspect its structured `accepts`, `tool`, `price`,
and recursively redacted `body` attributes. Account registration and plan
selection are not embedded in this protocol-level exception.

Three of them arrive on HTTP 402 and need opposite responses, which is the only
reason they are separate types. `HpsiMcpPaymentError` carries an offer a wallet
can settle — pay and retry. `HpsiMcpInsufficientCreditsError` means the balance
is empty — top up, and never retry as-is. `HpsiMcpAllowanceExhaustedError` is
the free evaluation ceiling for callers who have not identified themselves; no
payment lifts it, and it exposes `calls_used`, `calls_allowed`,
`calls_allowed_next`, `window_days`, and `next_actions` — whose first entry is
usually a `register_account` call taking only an email.

`HpsiMcpRateLimitError` uses a compact display string and exposes
`retry_after_seconds`, `limit`, `window`, and `tool` as attributes. Anonymous
clients receive only `register_url`; API-key Free clients receive only
`pricing_url`. Stored response context is recursively redacted.

Every one of them derives from `HpsiMcpError`. All but the last also derive
from `HpsiMcpAPIError` — `HpsiMcpSettlementUnknownError` is kept outside that
branch on purpose, so a blanket `except HpsiMcpAPIError: retry()` cannot catch
a payment that may already have settled and pay for it a second time.

### Unresolved settlements

A payment timeout may leave settlement status unknown. **Do not retry that
call** — the money may already have moved, and a retry pays twice for one
result. `HpsiMcpSettlementUnknownError` carries the `call_id`, `tool` and
`settlement_status` that reconciliation needs; `payment_spend_summary()` hands
you the ids of every call in this state.

API errors include `status_code` and redacted `response_text` when available.
Sensitive credential, signing, mnemonic, and wallet-shaped values are removed
from exception messages and stored response context.

`HpsiMcpConfigError` is also raised by the authentication circuit breaker.
After the first unresolved HTTP `401` or `402`, later calls on that Client
fail locally without sending a request. Recover with `set_api_key()`,
`set_wallet()`, or a new Client. HTTP `403` continues to raise
`HpsiMcpAuthError`.

Configuration errors use a summary/reason/fix layout. Do not retry a Client
that has opened its circuit before replacing its API Key or Wallet.

## Degraded responses

Anonymous callers share one daily pool across all tools rather than a
per-tool allowance. Once it is spent, a call is not simply refused: the API
replays the last known-good result for that exact request as an ordinary
`200`, marked with response headers —`X-HPSILAB-Degraded: true` and
`X-HPSILAB-Data-Age` (e.g. `"3h"`). The SDK does not surface these as a
distinct exception; treat any response you receive as possibly stale and
check for the pool having been exhausted via a preceding `429` if that
matters to your use case. Numbers returned this way are indicative, not
current — do not use them for anything time-sensitive.

## Payments

An anonymous caller with the daily pool spent — or calling a Pro tool, which
has no anonymous allowance at all — eventually gets **HTTP 402** carrying an
[x402](https://x402.org) challenge rather than a flat refusal. `402` is
therefore a normal, recoverable outcome, not a client bug.

**A wallet is not required.** Every challenge also names a card-checkout URL
(`https://hpsilab.com/pricing?anon=...`) for a human paying on behalf of a
wallet-less agent. That rail is register-then-pay; `register_account()` above
covers the registration half without a human.

Without a wallet the SDK does not retry a `402`. It raises
`HpsiMcpConfigError` and opens the Client's authentication circuit. Configure
a wallet with `set_wallet()`, replace the API key with `set_api_key()`, or
create a new Client before trying again.

With a wallet configured, the client signs the challenge and repeats the
request once. It never pays pre-emptively (the free call is attempted first),
never retries a second time, and refuses any challenge above
`max_price_usdc` (default `$1.00`). If signing fails or the paid retry still
returns `402`, the circuit opens and `HpsiMcpConfigError` is raised. Signing
is local — the key is not sent.

## Scope

This package is a REST API wrapper. It does not implement MCP transport, SSE,
streaming, tool discovery, Claude integration, or proprietary finance logic.
