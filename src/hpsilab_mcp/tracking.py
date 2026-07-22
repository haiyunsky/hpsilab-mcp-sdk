"""API tracking headers for outbound calls to the hpsilab backend.

Mirrors the helper used by the hpsilab-mcp MCP server (mcp_server/tracking.py)
so both callers attribute their traffic to `request_logs` the same way.
"""
from __future__ import annotations

from typing import Mapping, Optional


def build_tracking_headers(
    source: str,
    client: str,
    version: str,
    tool: Optional[str] = None,
    extra: Optional[Mapping[str, str]] = None,
) -> dict:
    """Build the `X-HPSILAB-*` header set for one outbound request.

    Never includes business headers (Authorization, API-Key, Content-Type, ...)
    — callers merge this dict into their own headers without it clobbering
    those, since the two header sets are disjoint by construction.
    """
    headers = {
        "X-HPSILAB-Source": source,
        "X-HPSILAB-Client": client,
        "X-HPSILAB-Version": version,
    }
    if tool:
        headers["X-HPSILAB-Tool"] = tool
    if extra:
        headers.update(extra)
    return headers
