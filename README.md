# H|ψ⟩ Quantum Finance MCP SDK

AI-powered quantitative finance tools via MCP.

Connect Claude, Codex, and AI agents directly to:

https://hpsilab.com/mcp

Features:

* AI Predictions
* IV Radar
* Option Pressure
* Monte Carlo Simulation
* Equity Curves

## Project Overview

H|ψ⟩ Quantum Finance MCP provides AI-powered quantitative finance tools through a hosted MCP endpoint. Client applications can use MCP to request structured stock analysis, AI prediction summaries, implied-volatility context, option pressure levels, Monte Carlo simulation ranges, equity curve metrics, and report assets.

This repository contains open-source SDK skeletons and examples for connecting MCP-compatible clients to the hosted H|ψ⟩ Quantum Finance MCP service.

This repository includes:

* Python SDK skeleton in `python/client.py`
* TypeScript SDK skeleton in `typescript/client.ts`
* Client setup examples in `examples/`
* Documentation for available MCP tools and prompt patterns

## Hosted MCP Endpoint

H|ψ⟩ Quantum Finance provides a hosted MCP endpoint:

https://hpsilab.com/mcp

No self-hosting required.

Connect directly from Claude Desktop, Codex, or other MCP-compatible clients.

## Quick Example

Once connected, ask:

* Analyze NVDA
* Predict IONQ
* Show IV Radar for QBTS
* Compare SOUN vs PLTR

## Setup

Configure your MCP-compatible client to connect to the hosted endpoint:

https://hpsilab.com/mcp

Typical MCP client configuration requires:

* The hosted MCP endpoint URL
* Any required client-side authentication configured outside this repository
* A client that supports MCP tool calls

Do not place secrets directly in this repository. Use your MCP client's supported secret or environment configuration mechanism.

## Quick Start

### Python

```python
from client import HpsiMcpClient

client = HpsiMcpClient(server_url="https://hpsilab.com/mcp")

analysis = client.call_tool(
    "analyze_stock",
    {"symbol": "NVDA"},
)

print(analysis)
```

### TypeScript

```ts
import { HpsiMcpClient } from "./client";

const client = new HpsiMcpClient({
  serverUrl: "https://hpsilab.com/mcp",
});

const analysis = await client.callTool("analyze_stock", {
  symbol: "NVDA",
});

console.log(analysis);
```

The SDK files are skeletons. Adapt transport, authentication, retries, and response validation to your runtime and MCP client stack.

## MCP Setup

An MCP client registers the hosted H|ψ⟩ endpoint under a named server entry, then exposes its tools to the assistant.

Example endpoint:

```text
https://hpsilab.com/mcp
```

Use your MCP client's supported remote-server configuration. Avoid committing credentials or local secrets.

## Claude Desktop Setup

Add the hosted endpoint to your Claude Desktop MCP configuration file.

Example:

```json
{
  "mcpServers": {
    "hpsilab": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://hpsilab.com/mcp"
      ]
    }
  }
}
```

Restart Claude Desktop after changing the MCP configuration. Once connected, Claude should be able to discover the H|ψ⟩ Quantum Finance MCP tools.

See `examples/claude-desktop.md` for a fuller setup template.

## Available Tools

Tool names may vary by deployment, but the public MCP surface is expected to include:

* `analyze_stock`: Aggregate stock research signal and summary data.
* `generate_stock_images`: Generate stock-report chart images.
* `generate_stock_research_report`: Generate a markdown research report with chart embeds.
* `get_ai_prediction`: Retrieve an AI-powered next-day directional prediction summary.
* `get_equity_curves`: Retrieve equity curve and backtest performance metrics.
* `get_iv_radar`: Retrieve implied-volatility structure and option sentiment context.
* `get_monte_carlo`: Retrieve a short-horizon Monte Carlo simulation summary.
* `get_option_pressure`: Retrieve option-chain pressure levels such as max pain and gamma context.

These tools return research-oriented information. They are not financial advice.

## Example Prompts

* "Analyze NVDA using the H|ψ⟩ Quantum Finance MCP tools and summarize the bullish and bearish factors."
* "Generate a stock research report for AAPL with charts."
* "Check IV Radar and Option Pressure for SPY."
* "Compare the Monte Carlo Simulation outlook and AI Prediction for TSLA."
* "Show the recent Equity Curves metrics for my watchlist."

## Repository Scope

This repository is for open-source client examples only. It deliberately excludes:

* Proprietary algorithms
* Internal model weights or prompts
* Trading strategy implementation details
* Server-side business logic
* Secrets, credentials, or private deployment configuration

## License

MIT. See `LICENSE`.
