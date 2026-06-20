# Codex Example

Codex can use H|ψ⟩ Quantum Finance MCP through the hosted MCP endpoint:

https://hpsilab.com/mcp

Example MCP server entry:

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

Once connected, Codex can call H|ψ⟩ Quantum Finance MCP tools directly using natural language.

Example prompts:

- Analyze TSLA
- Show IV Radar for NVDA
- Compare SOUN vs PLTR
- Generate a stock research report for MSFT
- Check Option Pressure for SPY
- Compare Monte Carlo Simulation and AI Prediction for QBTS
- Show Equity Curves for IONQ

Keep private deployment details and credentials outside this repository.
