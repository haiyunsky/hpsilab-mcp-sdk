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
2. Open **[Settings → Create key](https://hpsilab.com/settings)** and copy your
   `hpsi_...` key.

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
Trial. Invalid credentials fail instead of falling back to anonymous access.

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

Responses report usage through these headers:

```
X-Credits-Charged:   5
X-Credits-Remaining: 1995
```

Use `GET /api/credits/catalog` for current tool prices and
`GET /api/credits/balance` for the current balance. After adding Credits, call
`client.clear_insufficient_credits_circuit()` to recheck immediately.

### Errors and rate limits

Catch `HpsiMcpError` for one common SDK error boundary. Specific subclasses
include `HpsiMcpConfigError` for authentication,
`HpsiMcpInsufficientCreditsError` for an empty balance, and
`HpsiMcpRateLimitError` for rate limits.

## Paying without an account

As an alternative to an API key, install `hpsilab-mcp[x402]` and provide an
`X402Wallet`. The SDK can then pay supported tool calls in USDC on Base after
the server returns an x402 payment offer.

With a wallet, the client signs the challenge and repeats the request for you:

```python
from hpsilab_mcp import HpsiMcpClient, X402Wallet

try:
    client = HpsiMcpClient(wallet=X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
    print(client.get_monte_carlo("NVDA"))  # no account needed — paid per call
except Exception as e:
    print(f"HPSILab error: {e}")
```

Use `PaymentPolicy` to restrict per-call/session spending, assets, networks,
and payable tools. A wallet does not add Credits to an API-key account; add
Credits at <https://hpsilab.com/pricing> instead.

Payments are never made before the server presents an offer. Signing happens
locally, and the private key never leaves your process.

### Unresolved settlements

A payment timeout may leave settlement status unknown. Do not retry that call.
`HpsiMcpSettlementUnknownError` provides the `call_id`, `tool`, and
`settlement_status` needed for reconciliation.

Only tools included in the server's current x402 offer can be paid by wallet.
Use the live offer or Credits catalog instead of hard-coding prices.

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

The two `generate_*` methods create or refresh hosted artifacts and are not
guaranteed to be idempotent.

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

These tools return research-oriented information and are not financial advice.

## Links

- [Homepage](https://hpsilab.com)
- [Developer Portal](https://hpsilab.com/developer/v2)
- [Repository](https://github.com/haiyunsky/hpsilab-mcp-sdk)

## License

MIT. See `LICENSE`.
