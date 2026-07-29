# HPSILab Python REST SDK

`hpsilab-mcp` is the official Python SDK for the hosted hpsilab.com REST API — quantitative finance and options analytics (IV surface, Monte Carlo simulation, AI predictions, pre-trade risk scans, and more).

> **Note:** This package wraps REST endpoints only. It does not implement MCP transport — see [MCP Transport](#mcp-transport) below if you need that.

## Requirements

- Python >= 3.9

## Installation

```bash
pip install hpsilab-mcp
```

To let the client pay per call when the free quota runs out (see
[Paying past the free quota](#paying-past-the-free-quota)):

```bash
pip install "hpsilab-mcp[x402]"
```

## Quick Start

```python
from hpsilab_mcp import HpsiMcpClient

client = HpsiMcpClient()

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

<!-- TODO(Haiyun): confirm current tiering before publishing — see note below -->
All listed REST SDK methods are callable without an API key. The SDK does not block any method client-side; any access restrictions are enforced server-side.

```python
from hpsilab_mcp import HpsiMcpClient

client = HpsiMcpClient(
    api_key="YOUR_API_KEY",
    base_url="https://hpsilab.com",
)

result = client.get_ai_prediction("TSLA")
print(result)
```

Pass an `api_key` to raise rate limits or unlock account-specific features, where applicable.

## Paying past the free quota

Anonymous callers get a per-tool daily quota. Once it runs out — or when
calling a Pro tool, which has no anonymous allowance — the API answers **HTTP
402** with an [x402](https://x402.org) payment challenge instead of refusing
outright, so an agent can pay for the call in USDC on Base and keep working.

Without a wallet the SDK raises `HpsiMcpPaymentError` with the challenge
attached, and you can pay it however you like:

```python
from hpsilab_mcp import HpsiMcpClient, HpsiMcpPaymentError

try:
    client.get_monte_carlo("NVDA")
except HpsiMcpPaymentError as exc:
    print(exc.tool, exc.price)   # get_monte_carlo $0.10
    print(exc.accepts)           # scheme / network / asset / amount / payTo
```

With a wallet, the client signs the challenge and repeats the request for you:

```python
from hpsilab_mcp import HpsiMcpClient, X402Wallet

client = HpsiMcpClient(wallet=X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
client.get_monte_carlo("NVDA")   # free while quota lasts, paid after that
```

`X402Wallet()` reads `HPSILAB_X402_PRIVATE_KEY` when no key is passed, and a
client with no `wallet=` picks that variable up automatically. Three things
hold regardless of how it is configured:

* Nothing is paid pre-emptively — the free call is always attempted first.
* Each call is retried **once** after paying; a server that keeps answering
  402 cannot drain the wallet.
* `max_price_usdc` (default `$1.00`) caps a single call. A challenge asking for
  more is refused, not signed.

Signing happens locally; the private key never leaves your process.

| Tool | Price per call |
| --- | ---: |
| `analyze_stock`, `get_pretrade_risk_scan` | $0.15 |
| `get_monte_carlo` | $0.10 |
| `get_iv_radar`, `get_option_pressure`, `get_ai_prediction`, `get_equity_curve` | $0.05 |
| `generate_stock_research_report` | $0.35 |

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
