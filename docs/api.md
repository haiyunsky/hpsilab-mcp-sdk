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

## MCP Transport

All official MCP tools now have REST SDK coverage. Use an MCP-compatible client
when you specifically need MCP transport, tool discovery, or assistant-native
tool calls.

## Errors

The SDK exposes typed exceptions:

* `HpsiMcpError`
* `HpsiMcpConnectionError`
* `HpsiMcpTimeoutError`
* `HpsiMcpAPIError`
* `HpsiMcpAuthError`
* `HpsiMcpPaymentError`
* `HpsiMcpRateLimitError`
* `HpsiMcpResponseError`

API errors include `status_code` and `response_text` when available.

## Payments

An anonymous caller past a tool's free daily quota — or calling a Pro tool,
which has no anonymous allowance — gets **HTTP 402** carrying an
[x402](https://x402.org) challenge rather than a flat refusal. `402` is
therefore a normal, recoverable outcome, not a client bug.

Without a wallet the SDK raises `HpsiMcpPaymentError`, which carries the
challenge so you can pay it with your own x402 client:

| Attribute | Meaning |
| --- | --- |
| `accepts` | Payment options: `scheme`, `network`, `asset`, `amount`, `payTo` |
| `tool` | Tool the challenge is for |
| `price` | Display price, e.g. `"$0.10"` |
| `response_text` | Raw 402 body |

With a wallet configured, the client signs the challenge and repeats the
request once. It never pays pre-emptively (the free call is attempted first),
never retries a second time, and refuses any challenge above
`max_price_usdc` (default `$1.00`). Signing is local — the key is not sent.

## Scope

This package is a REST API wrapper. It does not implement MCP transport, SSE,
streaming, tool discovery, Claude integration, or proprietary finance logic.
