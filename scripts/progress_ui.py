from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class PlainProgress:
    def __init__(self, label: str, total: int) -> None:
        self.label = label
        self.total = total

    def update(self, completed: int, suffix: str = "") -> None:
        suffix_text = f" {suffix}" if suffix else ""
        print(f"{self.label}: {completed}/{self.total}{suffix_text}", flush=True)


@contextmanager
def progress_bar(label: str, total: int) -> Iterator[PlainProgress]:
    try:
        from rich.progress import (  # type: ignore[import-not-found]
            BarColumn,
            Progress,
            TextColumn,
            TimeRemainingColumn,
            TransferSpeedColumn,
        )
    except Exception:
        progress = PlainProgress(label, total)
        yield progress
        return

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="bright_magenta", finished_style="green"),
        TextColumn("[green]{task.completed}/{task.total}"),
        TextColumn("eta"),
        TimeRemainingColumn(),
    ) as rich_progress:
        task_id = rich_progress.add_task(label, total=total)

        class RichProgress:
            def update(self, completed: int, suffix: str = "") -> None:
                rich_progress.update(task_id, completed=completed, description=suffix or label)

        yield RichProgress()
