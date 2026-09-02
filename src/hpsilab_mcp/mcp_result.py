"""SDK-owned dependency metadata for MCP tool results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Generic, Mapping, Optional, TypeVar

T = TypeVar("T")
_TIME_KEYS = ("timestamp", "as_of", "asOf", "last_date", "lastDate", "data_time", "generated_at", "updated_at")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _opaque_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _iso8601(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value.isoformat()
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if len(candidate) == 10:
            try:
                return date.fromisoformat(candidate).isoformat()
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamps(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _TIME_KEYS:
                normalized = _iso8601(item)
                if normalized:
                    found.append(normalized)
            if isinstance(item, (Mapping, list, tuple)):
                found.extend(_timestamps(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_timestamps(item))
    return found


@dataclass(frozen=True)
class McpDependencyMetadata:
    """Dependency identifiers generated solely by this SDK."""

    result_id: str
    source_ids: list[str]
    upstream_ids: list[str]
    derived_from: list[str]
    timestamp: Optional[str]

    @property
    def raw(self) -> Mapping[str, Any]:
        return {
            "result_id": self.result_id,
            "source_ids": self.source_ids,
            "upstream_ids": self.upstream_ids,
            "derived_from": self.derived_from,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class McpToolResult(Generic[T]):
    """Opt-in business value plus SDK-owned dependency metadata."""

    data: T
    metadata: McpDependencyMetadata


def _field(result: Any, *names: str) -> Any:
    if isinstance(result, Mapping):
        for name in names:
            if name in result:
                return result[name]
        return None
    for name in names:
        if hasattr(result, name):
            return getattr(result, name)
    return None


def data_from_result(result: Any) -> Any:
    """Select the business value from a transport result."""
    structured = _field(result, "structuredContent", "structured_content")
    if structured is not None:
        return structured
    content = _field(result, "content")
    if content is None:
        return result
    if isinstance(content, list) and len(content) == 1:
        text = _field(content[0], "text")
        if text is not None:
            return text
    return content


def tool_error_message(result: Any) -> Optional[str]:
    """Return a failed tool's own error text, or ``None`` when it succeeded.

    MCP reports a *tool execution* failure inside an otherwise ordinary result
    — an ``isError`` flag beside the content — rather than as a protocol error,
    so the only thing separating it from a success is that flag. It is optional
    and absent means success.

    A tool that fails without saying why yields ``""``, not ``None``: callers
    must test ``is not None`` rather than truthiness.
    """
    if not _field(result, "isError", "is_error"):
        return None
    content = _field(result, "content")
    if isinstance(content, (list, tuple)):
        texts = [text for text in (_field(block, "text") for block in content) if isinstance(text, str)]
        if texts:
            return "\n".join(texts)
    return ""


def sdk_dependency_metadata(tool_name: str, arguments: Mapping[str, Any], data: Any, *, derived_from: Optional[list[str]] = None) -> McpDependencyMetadata:
    """Build deterministic metadata from SDK-visible inputs and output only."""
    normalized_arguments = dict(arguments)
    times = _timestamps(data)
    return McpDependencyMetadata(
        result_id=_opaque_id("res", {"tool": tool_name, "arguments": normalized_arguments, "data": data}),
        source_ids=[_opaque_id("src", normalized_arguments)] if normalized_arguments else [],
        upstream_ids=[_opaque_id("up", {"tool": tool_name, "arguments": normalized_arguments})],
        derived_from=list(dict.fromkeys(derived_from or [])),
        timestamp=max(times) if times else None,
    )


def full_tool_result(tool_name: str, arguments: Mapping[str, Any], result: Any, *, derived_from: Optional[list[str]] = None) -> McpToolResult[Any]:
    data = data_from_result(result)
    return McpToolResult(
        data=data,
        metadata=sdk_dependency_metadata(tool_name, arguments, data, derived_from=derived_from),
    )


__all__ = ["McpDependencyMetadata", "McpToolResult", "data_from_result", "full_tool_result", "sdk_dependency_metadata", "tool_error_message"]
