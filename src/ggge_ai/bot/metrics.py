"""Counters folded online from the tick log -- never a second source of truth."""

from __future__ import annotations


class Metrics:
    """Flat dotted keys, two instruments, process-local state.

    `count` is a monotonic counter; `observe` keeps n/sum/min/max for a value
    (no buckets, no histogram). There is no gauge -- board state is already a
    column of every tick record. Nothing here is written to disk and nothing
    survives the process: the tick log stays the single source of truth, and
    every tick-level counter must equal the same fold replayed over that log.
    """

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.observations: dict[str, tuple[int, int, int, int]] = {}

    def count(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + n

    def observe(self, key: str, value: int) -> None:
        seen = self.observations.get(key)
        if seen is None:
            self.observations[key] = (1, value, value, value)
            return
        n, total, low, high = seen
        self.observations[key] = (n + 1, total + value, min(low, value), max(high, value))

    def snapshot(self) -> dict[str, int]:
        flat = dict(self.counters)
        for key, (n, total, low, high) in self.observations.items():
            flat[f"{key}.n"] = n
            flat[f"{key}.sum"] = total
            flat[f"{key}.min"] = low
            flat[f"{key}.max"] = high
        return flat
