"""JSON artifact exporter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .base import ExportedArtifact


@dataclass
class JsonExporter:
    """Serialize arbitrary data as pretty JSON."""

    name: str = "finprog_export.json"
    output_type: str = "json"

    def export(self, data: Any) -> ExportedArtifact:
        return ExportedArtifact(
            name=self.name,
            media_type="application/json",
            content=json.dumps(data, indent=2, sort_keys=True, default=str) + "\n",
        )
