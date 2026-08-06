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

All listed REST SDK methods are callable without an API key. The SDK does not
block any method client-side.

Optional API key support is available when you want to send an Authorization
header:

```python
client = HpsiMcpClient(api_key="YOUR_API_KEY")
```

Do not commit API keys or local secrets.

### Anonymous key (automatic)

You do not need to do anything to get one. On your first successful call the
API issues a free key and the client adopts it automatically — every later
request on that client carries it, which raises your daily allowance
substantially:

```python
client = HpsiMcpClient()
client.get_monte_carlo("NVDA")
client.anon_key   # 'hpsi_anon_...' — issued and now in use
```

`anon_key` is `None` until one has been issued, and stays `None` for a client
built with `api_key=` — a real account's credential is never displaced by an
anonymous one.

To keep the larger allowance across processes, persist `client.anon_key` and
pass it back in:

```python
client = HpsiMcpClient(anon_key=saved_key)
```

The key is not tied to your IP address, so it survives address changes that
are normal on cloud hosts. If you exhaust the anonymous pool before a key was
ever issued, the resulting `429` carries one in its body; the client adopts it
and retries the call once, so the first time you hit the ceiling you get data
back instead of an exception. Asking again with the same identity returns the
same key rather than minting a new one.

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

The client adopts the returned account key (`anon_key` becomes `None`, since
no anonymous identity is in play any more). The account is *also* bound to the
caller server-side, so a process that cannot rewrite its own `Authorization`
header is still recognised on later calls.

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

## Errors

The SDK exposes typed exceptions:

* `HpsiMcpError`
* `HpsiMcpConfigError`
* `HpsiMcpConnectionError`
* `HpsiMcpTimeoutError`
* `HpsiMcpAPIError`
* `HpsiMcpAuthError`
* `HpsiMcpPaymentError`
* `HpsiMcpRateLimitError`
* `HpsiMcpResponseError`

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
