from hpsilab_mcp import HpsiMcpClient, HpsiMcpError


def get_prediction_with_metadata(api_key):
    try:
        client = HpsiMcpClient(api_key=api_key, base_url="https://hpsilab.com")
        result = client.get_ai_prediction("TSLA", include_metadata=True)
        print("Prediction:", result.data)
        # Generated locally by the SDK.
        print("Result ID:", result.metadata.result_id)
        print("Sources:", result.metadata.source_ids)
        print("Upstream:", result.metadata.upstream_ids)
        print("Derived from:", result.metadata.derived_from)
        print("Timestamp:", result.metadata.timestamp)
        return result
    except HpsiMcpError as e:
        print(f"Prediction request failed: {e}")
        return None


# result = get_prediction_with_metadata("YOUR_API_KEY")
