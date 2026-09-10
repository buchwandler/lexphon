"""Dependency-free progress reporting for pronunciation benchmarks."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TextIO


@dataclass
class ProgressReporter:
    """Write bounded benchmark progress messages to a stream."""

    enabled: bool = True
    stream: TextIO = field(default_factory=lambda: sys.stderr)

    def __post_init__(self) -> None:
        self._next_counts: dict[tuple[str, str, int], int] = {}

    def emit(self, message: str) -> None:
        if not self.enabled:
            return
        print(message, file=self.stream, flush=True)

    def benchmark(self, index: int, total: int, lexicon_id: str) -> None:
        self.emit(f"[{index}/{total}] {lexicon_id}")

    def stage(self, lexicon_id: str, name: str, message: str) -> None:
        self.emit(f"[{lexicon_id}] {name}: {message}")

    def counter(
        self,
        lexicon_id: str,
        name: str,
        current: int,
        total: int,
        *,
        suffix: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        if total <= 0:
            return
        key = (lexicon_id, name, total)
        step = max(1, total // 5)
        next_count = self._next_counts.get(key, step)
        if current < total and current < next_count:
            return
        while next_count <= current and next_count < total:
            next_count += step
        if current >= total:
            next_count = total + step
        self._next_counts[key] = next_count
        detail = f"; {suffix}" if suffix else ""
        self.stage(lexicon_id, name, f"{current}/{total}{detail}")
