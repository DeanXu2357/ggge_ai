from __future__ import annotations

from collections.abc import Iterator, Mapping

Value = bool | int | float | str


class WorldState(Mapping[str, Value]):
    """Immutable symbolic world state; hashable so the planner can dedupe visited states."""

    __slots__ = ("_facts", "_hash")

    def __init__(self, facts: Mapping[str, Value] | None = None, **kwargs: Value) -> None:
        merged = dict(facts) if facts else {}
        merged.update(kwargs)
        self._facts: dict[str, Value] = merged
        self._hash: int | None = None

    def __getitem__(self, key: str) -> Value:
        return self._facts[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._facts)

    def __len__(self) -> int:
        return len(self._facts)

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(frozenset(self._facts.items()))
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, WorldState):
            return self._facts == other._facts
        return NotImplemented

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}={v!r}" for k, v in sorted(self._facts.items()))
        return f"WorldState({inner})"

    def with_updates(self, updates: Mapping[str, Value]) -> WorldState:
        merged = dict(self._facts)
        merged.update(updates)
        return WorldState(merged)

    def satisfies(self, conditions: Mapping[str, Value]) -> bool:
        return all(self._facts.get(k) == v for k, v in conditions.items())

    def count_unmet(self, conditions: Mapping[str, Value]) -> int:
        return sum(1 for k, v in conditions.items() if self._facts.get(k) != v)
