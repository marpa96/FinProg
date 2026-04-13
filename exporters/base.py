"""Shared contracts for exporter modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ExportedArtifact:
    """A generated output artifact such as CSV, JSON, or markdown."""

    name: str
    media_type: str
    content: str | bytes
    metadata: dict[str, Any | None] = field(default_factory=dict)


class Exporter(Protocol):
    """Interface for one output-format exporter."""

    output_type: str

    def export(self, data: Any) -> ExportedArtifact:
        """Serialize data into the exporter's target format."""
