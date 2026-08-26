from __future__ import annotations

from types import SimpleNamespace

import pytest

from hpsilab_mcp import HpsiMcpClient, HpsiMcpConfigError, McpToolResult


RAW_META = {
    "result_id": "res_nvda_prediction",
    "source_ids": ["src_nvda_close"],
    "upstream_ids": ["up_nvda_signal"],
    "derived_from": [],
    "timestamp": "2026-08-25",
    "server_extension": {"kept": True},
}


def test_include_metadata_reads_call_tool_result_meta_without_regeneration():
    raw_result = SimpleNamespace(
        structuredContent={"symbol": "NVDA", "signal": "bullish"},
        content=[],
        meta=RAW_META,
    )
    seen = []

    def transport(name, arguments):
        seen.append((name, arguments))
        return raw_result

    client = HpsiMcpClient(mcp_transport=transport)
    result = client.call_tool(
        "get_ai_prediction", ticker="NVDA", include_metadata=True
    )

    assert isinstance(result, McpToolResult)
    assert result.data == raw_result.structuredContent
    assert result.metadata is not None
    assert result.metadata.raw is RAW_META
    assert result.metadata.result_id == RAW_META["result_id"]
    assert result.metadata.source_ids == RAW_META["source_ids"]
    assert result.metadata.upstream_ids == RAW_META["upstream_ids"]
    assert result.metadata.derived_from == RAW_META["derived_from"]
    assert result.metadata.timestamp == RAW_META["timestamp"]
    assert seen == [("get_ai_prediction", {"ticker": "NVDA"})]
    client.close()


def test_default_call_tool_return_remains_the_transport_value():
    raw_result = {"content": [{"type": "text", "text": "unchanged"}], "_meta": RAW_META}
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    assert client.call_tool("get_ai_prediction", ticker="NVDA") is raw_result
    client.close()


def test_decoded_wire_meta_key_is_passed_through_exactly():
    raw_result = {
        "structuredContent": {"symbol": "NVDA"},
        "content": [],
        "_meta": RAW_META,
    }
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    result = client.call_tool("analyze_stock", symbol="NVDA", include_metadata=True)
    assert result.metadata is not None
    assert result.metadata.raw is raw_result["_meta"]
    assert result.metadata.raw == RAW_META
    client.close()


def test_missing_metadata_is_safe_and_text_data_is_unwrapped():
    raw_result = {"content": [{"type": "text", "text": "NVDA prediction"}]}
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    result = client.call_tool("get_ai_prediction", ticker="NVDA", include_metadata=True)
    assert result.data == "NVDA prediction"
    assert result.metadata is None
    client.close()


def test_partial_metadata_exposes_none_and_empty_collections():
    raw_result = {"structuredContent": {"ok": True}, "_meta": {"result_id": "res_1"}}
    client = HpsiMcpClient(mcp_transport=lambda name, arguments: raw_result)
    metadata = client.call_tool("analyze_stock", symbol="NVDA", include_metadata=True).metadata
    assert metadata is not None
    assert metadata.result_id == "res_1"
    assert metadata.source_ids == []
    assert metadata.upstream_ids == []
    assert metadata.derived_from == []
    assert metadata.timestamp is None
    client.close()


def test_call_tool_requires_an_explicit_transport_adapter():
    client = HpsiMcpClient()
    with pytest.raises(HpsiMcpConfigError, match="mcp_transport"):
        client.call_tool("get_ai_prediction", ticker="NVDA")
    client.close()
