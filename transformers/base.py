"""Shared contracts for transformation modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict

from extractors import ExtractedPayload


class FinProgTransaction(TypedDict, total=False):
    """Transaction shape used by the FinProg engine and web app."""

    id: str | None
    name: str | None
    type: str | None
    kind: str | None
    cashflowClass: str | None
    amount: float | None
    frequency: str | None
    startDate: str | None
    endDate: str | None
    active: bool | None
    categoryId: str | None
    subcategoryId: str | None
    savingsRulePercent: float | None
    schedule: dict[str, Any] | None


@dataclass(frozen=True)
class TransformResult:
    """Normalized output from a transformer.

    Unknown or unavailable values should stay as ``None`` so downstream code can
    decide whether to infer, prompt, skip, or preserve them.
    """

    transactions: list[FinProgTransaction] = field(default_factory=list)
    metadata: dict[str, Any | None] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


class Transformer(Protocol):
    """Interface for one extracted-format to FinProg-format transformer."""

    input_type: str

    def transform(self, payload: ExtractedPayload) -> TransformResult:
        """Convert extracted data into FinProg-useful structures."""
