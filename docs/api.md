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

## Methods

```python
client.analyze_stock("NVDA")
client.get_ai_prediction("NVDA")
client.get_iv_radar("NVDA")
client.get_option_pressure("SPY")
client.get_pretrade_risk_scan("NVDA")
client.get_monte_carlo("QBTS")
client.get_equity_curve("IONQ")
client.get_equity_curves("IONQ")
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
| `get_equity_curves(symbol)` | `GET /api/equity_curve/{symbol}` |
| `generate_stock_images(symbol)` | `POST /api/stock_report/{symbol}/images` |
| `generate_stock_research_report(symbol)` | `POST /api/stock_report/{symbol}/research_report` |

MCP behavior annotations belong to the MCP server and are not emitted by this
REST SDK. The `GET` methods are read-only. The two `generate_*` methods create
or refresh hosted artifacts and may consume quota or trigger payment; callers
should not assume repeated requests are idempotent.

`get_equity_curve(symbol)` remains available as a backwards-compatible alias
for `get_equity_curves(symbol)`.

## Capability Matrix

| Capability | REST API | MCP |
| --- | --- | --- |
| `analyze_stock` | Yes | Yes |
| `get_ai_prediction` | Yes | Yes |
| `get_iv_radar` | Yes | Yes |
| `get_option_pressure` | Yes | Yes |
| `get_pretrade_risk_scan` | Yes | Yes |
| `get_monte_carlo` | Yes | Yes |
| `get_equity_curve` | Yes | No |
| `get_equity_curves` | Yes | Yes |
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
* `HpsiMcpRateLimitError`
* `HpsiMcpResponseError`

API errors include `status_code` and `response_text` when available.

## Scope

This package is a REST API wrapper. It does not implement MCP transport, SSE,
streaming, tool discovery, Claude integration, or proprietary finance logic.
