"""Shared contracts for extraction modules.

Extractor modules are responsible only for pulling information out of a source
and preserving enough context for a transformer to interpret it later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ExtractedPayload:
    """Raw information plus source metadata from an extraction step."""

    source_type: str
    payload: Any
    source_name: str | None = None
    metadata: dict[str, Any | None] = field(default_factory=dict)


class Extractor(Protocol):
    """Interface for one source/type-specific extractor."""

    source_type: str

    def extract(self, source: Any) -> ExtractedPayload:
        """Return raw source information without shaping it for FinProg."""
