# OpenAI Agents Example

OpenAI Agents can connect directly to the hosted H|ψ⟩ Quantum Finance MCP endpoint through an MCP-compatible tool adapter.

Hosted MCP endpoint:

https://hpsilab.com/mcp

No self-hosting required.

Conceptual setup:

```python
from client import HpsiMcpClient

client = HpsiMcpClient(server_url="https://hpsilab.com/mcp")

result = client.call_tool(
    "analyze_stock",
    {"symbol": "NVDA"},
)

print(result)
```

Example agent instructions:

```text
You are a finance research assistant. Use H|ψ⟩ Quantum Finance MCP tools
when the user asks for stock analysis, option pressure, implied volatility,
Monte Carlo ranges, AI prediction summaries, or research reports.
```

Example prompts:

- Analyze NVDA
- Show IV Radar for QQQ
- Check Option Pressure for SPY
- Compare Monte Carlo Simulation and AI Prediction for QBTS
- Generate a stock research report for AAPL

This repository provides SDK skeletons only. Add production transport, authentication, tracing, validation, and error handling in your application code.
