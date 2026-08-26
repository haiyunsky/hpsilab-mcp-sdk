"""Types and decoding helpers for optional MCP tool-result metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Mapping, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class McpDependencyMetadata:
    """Read-only view of fields supplied by ``CallToolResult._meta``.

    Values are never generated or inferred by the SDK. ``raw`` retains the
    complete MCP metadata mapping, including unrelated server extensions.
    """

    raw: Mapping[str, Any]

    @property
    def result_id(self) -> Optional[str]:
        return self.raw.get("result_id")

    @property
    def source_ids(self) -> list[str]:
        value = self.raw.get("source_ids")
        return value if isinstance(value, list) else []

    @property
    def upstream_ids(self) -> list[str]:
        value = self.raw.get("upstream_ids")
        return value if isinstance(value, list) else []

    @property
    def derived_from(self) -> list[str]:
        value = self.raw.get("derived_from")
        return value if isinstance(value, list) else []

    @property
    def timestamp(self) -> Optional[str]:
        return self.raw.get("timestamp")


@dataclass(frozen=True)
class McpToolResult(Generic[T]):
    """Opt-in full MCP return value."""

    data: T
    metadata: Optional[McpDependencyMetadata]


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


def dependency_metadata_from_result(result: Any) -> Optional[McpDependencyMetadata]:
    """Return the exact MCP ``_meta`` mapping, or ``None`` when absent."""
    raw = _field(result, "_meta", "meta")
    if not isinstance(raw, Mapping):
        return None
    return McpDependencyMetadata(raw=raw)


def data_from_result(result: Any) -> Any:
    """Select the business value from a raw MCP CallToolResult."""
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


def full_tool_result(result: Any) -> McpToolResult[Any]:
    return McpToolResult(
        data=data_from_result(result),
        metadata=dependency_metadata_from_result(result),
    )


__all__ = [
    "McpDependencyMetadata",
    "McpToolResult",
    "dependency_metadata_from_result",
    "full_tool_result",
]
