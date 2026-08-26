from hpsilab_mcp import HpsiMcpClient


def get_prediction_with_metadata(call_tool):
    """call_tool comes from your configured synchronous MCP client."""
    try:
        client = HpsiMcpClient(mcp_transport=call_tool)
        result = client.call_tool(
            "get_ai_prediction",
            ticker="NVDA",
            include_metadata=True,
        )
        print("Prediction:", result.data)
        # Generated locally by the SDK.
        print("Result ID:", result.metadata.result_id)
        print("Sources:", result.metadata.source_ids)
        print("Upstream:", result.metadata.upstream_ids)
        print("Derived from:", result.metadata.derived_from)
        print("Timestamp:", result.metadata.timestamp)
        return result
    except Exception as e:
        print(f"HPSILab MCP error: {e}")
        return None


# Supply the synchronous call_tool function from your configured MCP client:
# result = get_prediction_with_metadata(mcp_client.call_tool)
