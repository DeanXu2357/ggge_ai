from __future__ import annotations

import json
from collections.abc import Hashable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

BASELINE = Path(__file__).with_name("tolerance_baseline.json")
UPDATE_OPTION = "--update-tolerance-baseline"
TALLIES = pytest.StashKey[dict[str, "Tally"]]()


@dataclass(frozen=True)
class CaseDifference:
    case_id: str
    missed: frozenset[Hashable]
    extra: frozenset[Hashable]


@dataclass
class Tally:
    correct: int = 0
    missed: int = 0
    extra: int = 0
    differences: list[CaseDifference] = field(default_factory=lambda: [])

    def add(self, case_id: str, read: Iterable[Hashable], ruled: Iterable[Hashable]) -> None:
        read_set, ruled_set = frozenset(read), frozenset(ruled)
        missed, extra = ruled_set - read_set, read_set - ruled_set
        self.correct += len(read_set & ruled_set)
        self.missed += len(missed)
        self.extra += len(extra)
        if missed or extra:
            self.differences.append(CaseDifference(case_id, missed, extra))

    @property
    def ruled(self) -> int:
        return self.correct + self.missed

    @property
    def read(self) -> int:
        return self.correct + self.extra

    @property
    def recognition(self) -> float:
        return self.correct / self.ruled if self.ruled else 1.0

    @property
    def false_read(self) -> float:
        return self.extra / self.read if self.read else 0.0

    def numbers(self) -> dict[str, float]:
        return {
            "recognition": self.recognition,
            "false_read": self.false_read,
            "correct": self.correct,
            "missed": self.missed,
            "extra": self.extra,
        }


def check_against_baseline(config: pytest.Config, capability: str, tally: Tally) -> None:
    config.stash.setdefault(TALLIES, {})[capability] = tally
    baseline = _load()
    if config.getoption(UPDATE_OPTION):
        baseline[capability] = tally.numbers()
        BASELINE.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
        return
    assert capability in baseline, f"{capability} has no baseline; run pytest {UPDATE_OPTION}"
    expected = baseline[capability]
    assert tally.recognition >= expected["recognition"], (
        f"{capability} recognition {tally.recognition:.3f} < baseline "
        f"{expected['recognition']:.3f}\n{describe(capability, tally)}"
    )
    assert tally.false_read <= expected["false_read"], (
        f"{capability} false read {tally.false_read:.3f} > baseline "
        f"{expected['false_read']:.3f}\n{describe(capability, tally)}"
    )


def describe(capability: str, tally: Tally) -> str:
    lines = [
        f"{capability}: recognition {tally.recognition:.3f} ({tally.correct}/{tally.ruled}), "
        f"false read {tally.false_read:.3f} ({tally.extra}/{tally.read})"
    ]
    for difference in tally.differences:
        lines.append(
            f"  {difference.case_id}: missed {sorted(difference.missed, key=repr)} "
            f"extra {sorted(difference.extra, key=repr)}"
        )
    return "\n".join(lines)


def _load() -> dict[str, dict[str, float]]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text())
