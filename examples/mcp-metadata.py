from hpsilab_mcp import HpsiMcpClient


# Adapt your MCP client's synchronous call_tool function. It must return the
# original MCP CallToolResult (or its decoded JSON representation).
def mcp_call(tool_name, arguments):
    return configured_mcp_session.call_tool(tool_name, arguments)  # noqa: F821


client = HpsiMcpClient(mcp_transport=mcp_call)
result = client.call_tool(
    "get_ai_prediction",
    ticker="NVDA",
    include_metadata=True,
)

print(result.data)
if result.metadata is not None:
    print(result.metadata.result_id)
    print(result.metadata.source_ids)
    print(result.metadata.upstream_ids)
    print(result.metadata.derived_from)
    print(result.metadata.timestamp)
