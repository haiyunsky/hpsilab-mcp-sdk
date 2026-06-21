from hpsilab_mcp import HpsiMcpClient

client = HpsiMcpClient()

rest_methods = [
    "analyze_stock",
    "get_ai_prediction",
    "get_iv_radar",
    "get_option_pressure",
    "get_monte_carlo",
    "get_equity_curve",
    "get_equity_curves",
    "generate_stock_images",
    "generate_stock_research_report",
]

mcp_only = []

print([name for name in rest_methods if hasattr(client, name)])
print([name for name in mcp_only if hasattr(client, name)])
