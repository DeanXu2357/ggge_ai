from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np

from ggge_ai_2.interpreter.contract import AutoMode

LABELED = Path(__file__).resolve().parents[2] / "data" / "labeled"
CASES = LABELED / "cases.jsonl"
FRAMES = LABELED / "frames"


@dataclass(frozen=True)
class MapLabel:
    cells: frozenset[tuple[int, int]]
    borders: frozenset[str]
    units: frozenset[tuple[tuple[int, int], tuple[int, int]]]
    controllable: frozenset[tuple[int, int]]
    occupied: frozenset[tuple[int, int]]


@dataclass(frozen=True)
class Case:
    id: str
    source: str
    index: int
    file: str
    t: float | None
    sha256: str
    screen: str
    transition: bool
    auto: AutoMode | None
    power_save: str | None
    map: MapLabel | None


@functools.cache
def cases() -> tuple[Case, ...]:
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]
    return tuple(_case(row) for row in rows)


def _case(row: dict[str, object]) -> Case:
    auto = row["auto"]
    return Case(
        id=str(row["id"]),
        source=str(row["source"]),
        index=int(str(row["index"])),
        file=str(row["file"]),
        t=None if row["t"] is None else float(str(row["t"])),
        sha256=str(row["sha256"]),
        screen=str(row["screen"]),
        transition=row["transition"] is True,
        auto=None if auto is None else AutoMode(str(auto)),
        power_save=None if row["power_save"] is None else str(row["power_save"]),
        map=None if row["map"] is None else _map_label(cast(dict[str, Any], row["map"])),
    )


def _map_label(label: dict[str, Any]) -> MapLabel:
    def cells(key: str) -> frozenset[tuple[int, int]]:
        return frozenset((int(x), int(y)) for x, y in label[key])

    return MapLabel(
        cells=cells("cells"),
        borders=frozenset(str(edge) for edge in label["borders"]),
        units=frozenset(
            (
                (int(unit["pos"][0]), int(unit["pos"][1])),
                (int(unit["size"][0]), int(unit["size"][1])),
            )
            for unit in label["units"]
        ),
        controllable=cells("controllable"),
        occupied=frozenset(
            cell for unit in label["units"] for cell in _footprint(unit) + _extra(unit)
        ),
    )


def _footprint(unit: dict[str, Any]) -> list[tuple[int, int]]:
    (column, row), (width, height) = unit["pos"], unit["size"]
    return [(int(column) + dx, int(row) + dy) for dx in range(width) for dy in range(height)]


def _extra(unit: dict[str, Any]) -> list[tuple[int, int]]:
    return [(int(column), int(row)) for column, row in unit.get("extra", [])]


def load_image(case: Case) -> np.ndarray:
    path = FRAMES / case.file
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(path)
    return np.asarray(image)
