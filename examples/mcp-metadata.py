from hpsilab_mcp import HpsiMcpClient, HpsiMcpError


def analyze_with_metadata(mcp_call_tool):
    """Use a configured synchronous MCP client's call_tool function."""
    try:
        client = HpsiMcpClient(mcp_transport=mcp_call_tool)
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
        return result
    except HpsiMcpError as exc:
        print(f"HPSILab MCP request failed: {exc}")
        return None


# Supply the synchronous call_tool function from your configured MCP client:
# result = analyze_with_metadata(your_mcp_client.call_tool)
