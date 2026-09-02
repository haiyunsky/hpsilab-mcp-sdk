from __future__ import annotations

import pytest
import httpx

from hpsilab_mcp import HpsiMcpClient, HpsiMcpConfigError, HpsiMcpToolError, McpToolResult


def test_rest_prediction_can_include_sdk_metadata():
    def handler(request):
        assert request.url.path == "/api/ai_prediction/TSLA"
        return httpx.Response(
            200,
            json={"symbol": "TSLA", "signal": "bullish", "as_of": "2026-08-25"},
        )

    client = HpsiMcpClient(
        api_key="hpsi_test",
        transport=httpx.MockTransport(handler),
    )
    result = client.get_ai_prediction("TSLA", include_metadata=True)

    assert isinstance(result, McpToolResult)
    assert result.data["symbol"] == "TSLA"
    assert result.metadata.result_id.startswith("res_")
    assert result.metadata.source_ids
    assert result.metadata.upstream_ids
    assert result.metadata.derived_from == []
    assert result.metadata.timestamp == "2026-08-25"
    client.close()

def test_sdk_generates_stable_metadata_for_fixed_nvda_result():
    raw_result = {
        "structuredContent": {
            "symbol": "NVDA",
            "signal": "bullish",
            "as_of": "2026-08-25",
        },
        "content": [],
    }
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    first = client.call_tool("get_ai_prediction", ticker="NVDA", include_metadata=True)
    second = client.call_tool("get_ai_prediction", ticker="NVDA", include_metadata=True)
    assert isinstance(first, McpToolResult)
    assert first.data == raw_result["structuredContent"]
    assert first.metadata == second.metadata
    assert first.metadata.result_id.startswith("res_")
    assert first.metadata.source_ids[0].startswith("src_")
    assert first.metadata.upstream_ids[0].startswith("up_")
    assert first.metadata.derived_from == []
    assert first.metadata.timestamp == "2026-08-25"
    client.close()


def test_ids_change_when_normalized_call_changes():
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: {"symbol": "NVDA", "value": 1})
    baseline = client.call_tool("analyze_stock", symbol="NVDA", include_metadata=True)
    other = client.call_tool("analyze_stock", symbol="NVDA", refresh=True, include_metadata=True)
    assert baseline.metadata.result_id != other.metadata.result_id
    assert baseline.metadata.source_ids != other.metadata.source_ids
    assert baseline.metadata.upstream_ids != other.metadata.upstream_ids
    client.close()


def test_default_call_tool_return_remains_the_transport_value():
    raw_result = {"content": [{"type": "text", "text": "unchanged"}]}
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    assert client.call_tool("get_ai_prediction", ticker="NVDA") is raw_result
    client.close()


def test_missing_timestamp_is_safe_and_text_data_is_unwrapped():
    raw_result = {"content": [{"type": "text", "text": "NVDA prediction"}]}
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    result = client.call_tool("get_ai_prediction", ticker="NVDA", include_metadata=True)
    assert result.data == "NVDA prediction"
    assert result.metadata.timestamp is None
    assert set(result.metadata.raw) == {"result_id", "source_ids", "upstream_ids", "derived_from", "timestamp"}
    client.close()


def test_call_tool_requires_an_explicit_transport_adapter():
    client = HpsiMcpClient()
    with pytest.raises(HpsiMcpConfigError, match="mcp_transport"):
        client.call_tool("get_ai_prediction", ticker="NVDA")
    client.close()


def test_a_tool_execution_error_is_raised_rather_than_returned_as_data():
    """MCP puts a failed tool's own error text in `content` and sets `isError`
    beside it, so the failure arrives shaped exactly like a success. Reading it
    as business output is the whole hazard this flag exists to prevent."""
    raw_result = {
        "content": [{"type": "text", "text": "Invalid ticker: NVDAA"}],
        "isError": True,
    }
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    with pytest.raises(HpsiMcpToolError) as caught:
        client.call_tool("get_ai_prediction", ticker="NVDAA", include_metadata=True)
    assert caught.value.tool_name == "get_ai_prediction"
    assert caught.value.message == "Invalid ticker: NVDAA"
    client.close()


def test_the_default_path_raises_too_so_no_caller_reads_a_failure_as_a_value():
    """`include_metadata=False` documents the adapter's original value as the
    return, but a failed call has no value: the content *is* the error text,
    and returning it makes the failure indistinguishable from a string result.
    With `include_metadata=True` the same result would additionally mint a
    well-formed provenance record for a call that produced nothing."""
    raw_result = {"content": [{"type": "text", "text": "upstream timeout"}], "isError": True}
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    with pytest.raises(HpsiMcpToolError, match="upstream timeout"):
        client.call_tool("get_ai_prediction", ticker="NVDA")
    client.close()


def test_an_explicit_false_error_flag_is_still_a_success():
    raw_result = {"structuredContent": {"symbol": "NVDA"}, "isError": False}
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    result = client.call_tool("get_ai_prediction", ticker="NVDA", include_metadata=True)
    assert result.data == {"symbol": "NVDA"}
    client.close()


def test_a_tool_that_fails_without_saying_why_still_raises():
    """`isError` carries the failure; the text is optional and the blocks need
    not be text at all. Keying on the message would let the quietest failures
    through as successes."""
    raw_result = {
        "content": [{"type": "image", "data": "AAAA", "mimeType": "image/png"}],
        "isError": True,
    }
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    with pytest.raises(HpsiMcpToolError) as caught:
        client.call_tool("get_ai_prediction", ticker="NVDA")
    assert caught.value.message == ""
    client.close()


def test_a_tool_error_message_is_redacted_like_every_other_error():
    raw_result = {
        "content": [{"type": "text", "text": "rejected key hpsi_live_abcdef123456"}],
        "isError": True,
    }
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    with pytest.raises(HpsiMcpToolError) as caught:
        client.call_tool("get_ai_prediction", ticker="NVDA")
    assert "hpsi_live_abcdef123456" not in str(caught.value)
    assert "[REDACTED]" in caught.value.message
    client.close()
