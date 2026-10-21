from __future__ import annotations

from typing import Any, Protocol


class SourceAdapter(Protocol):
    source_id: str

    def normalize(self, *, raw: bytes, source: dict[str, Any],
                  overlay: dict[str, Any] | None,
                  identity: dict[str, Any]) -> dict[str, Any]:
        """纯转换；不联网、不写数据库、不改变已有审核。"""
        ...
