"""Extractor for Rocket Money CSV exports.

This module intentionally keeps data raw. Transformation into FinProg's
cashflow model belongs in a transformer, not in the extractor.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from extractors.base import ExtractedPayload


class RocketMoneyCsvExtractor:
    """Read a Rocket Money CSV export into raw row dictionaries."""

    source_type = "rocket_money.csv"

    def extract(self, source: str | Path) -> ExtractedPayload:
        path = Path(source)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows: list[dict[str, Any]] = list(csv.DictReader(handle))

        return ExtractedPayload(
            source_type=self.source_type,
            source_name=path.name,
            payload=rows,
            metadata={
                "path": str(path),
                "row_count": len(rows),
                "columns": list(rows[0].keys()) if rows else [],
            },
        )
