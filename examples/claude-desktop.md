# Claude Desktop Example

This example shows how to connect Claude Desktop directly to the hosted H|ψ⟩ Quantum Finance MCP endpoint.

Hosted MCP endpoint:

https://hpsilab.com/mcp

No self-hosting required.

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

After saving the configuration, restart Claude Desktop and confirm that the H|ψ⟩ Quantum Finance MCP tools are available from the hosted endpoint.

Example prompts:

- "Use H|ψ⟩ Quantum Finance MCP to analyze NVDA."
- "Generate a research report for AAPL."
- "Check IV radar and option pressure for SPY."

Do not store secrets directly in this repository or in shared configuration snippets.
