# Python SDK API

The `hpsilab-mcp` package provides a lightweight synchronous REST API wrapper
for H|ψ⟩ Quantum Finance.

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

Optional API key support is available for future paid plans:

```python
client = HpsiMcpClient(api_key="YOUR_API_KEY")
```

Do not commit API keys or local secrets.

## Methods

```python
client.get_ai_prediction("NVDA")
client.get_iv_radar("NVDA")
client.get_option_pressure("SPY")
client.get_equity_curve("IONQ")
client.get_equity_curves("IONQ")
client.get_monte_carlo("QBTS")
```

Endpoint mapping:

| Method | Endpoint |
| --- | --- |
| `get_ai_prediction(symbol)` | `GET /api/ai_prediction/{symbol}` |
| `get_iv_radar(symbol)` | `GET /api/iv_batch?symbols={symbol}` |
| `get_option_pressure(symbol)` | `GET /api/option_pressure/{symbol}` |
| `get_equity_curve(symbol)` | `GET /api/equity_curve/{symbol}` |
| `get_monte_carlo(symbol)` | `GET /api/monte_carlo/{symbol}` |

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
