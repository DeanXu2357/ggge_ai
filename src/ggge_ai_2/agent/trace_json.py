"""The JSON form of the plan trace: map reading records, the planning state of a belief, and
gestures.

The run log keeps this form so that a later code version can still read an old run.
"""

from __future__ import annotations

import base64
from typing import Any

import numpy as np

from ggge_ai_2.actuator.contract import Key, Swipe, Tap
from ggge_ai_2.agent.belief import Belief
from ggge_ai_2.agent.contract import MapReadingRecord, MapTap
from ggge_ai_2.interpreter.contract import Phase
from ggge_ai_2.mapparser.contract import (
    CellPlace,
    CellReading,
    Edge,
    MapReading,
    Marker,
    MechPanel,
    NameTemplate,
    PanelIcon,
    PilotPanel,
    PilotState,
    TapMarkReading,
    Terrain,
    UnitPanel,
    UnitReading,
)
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import OpenGroup, UiAutoMode, UiScreen, UiState, UiUnitList

Json = dict[str, Any]


def encode_record(record: MapReadingRecord) -> Json:
    reading = record.reading
    return {
        "still": _encode_still(record.still),
        "phase": None if record.phase is None else record.phase.value,
        "turn": record.turn,
        "cells": [[*cell, value.value] for cell, value in sorted(reading.cells.items())],
        "borders": sorted(edge.value for edge in reading.borders),
        "units": [
            {
                "pos": list(unit.pos),
                "size": list(unit.size),
                "controllable": unit.controllable,
                "selected": unit.selected,
                "enemy_selected": unit.enemy_selected,
                "cropped": unit.cropped,
            }
            for unit in reading.units
        ],
        "markers": [
            [*cell, sorted(marker.value for marker in markers)]
            for cell, markers in sorted(reading.markers.items())
        ],
        "places": [
            [*cell, list(place.center), [list(corner) for corner in place.corners]]
            for cell, place in sorted(reading.places.items())
        ],
        "panel": _encode_panel(reading.panel),
        "enemy_panel": _encode_panel(reading.enemy_panel),
        "tap_mark": None
        if reading.tap_mark is None
        else {
            "cell": list(reading.tap_mark.cell),
            "terrain": None
            if reading.tap_mark.terrain is None
            else [terrain.value for terrain in reading.tap_mark.terrain],
        },
    }


def decode_record(data: Json) -> MapReadingRecord:
    tap_mark = data["tap_mark"]
    reading = MapReading(
        cells={(x, y): CellReading(value) for x, y, value in data["cells"]},
        borders=frozenset(Edge(edge) for edge in data["borders"]),
        units=tuple(
            UnitReading(
                pos=_pair(unit["pos"]),
                size=_pair(unit["size"]),
                controllable=unit["controllable"],
                selected=unit["selected"],
                enemy_selected=unit["enemy_selected"],
                cropped=unit["cropped"],
            )
            for unit in data["units"]
        ),
        markers={
            (x, y): frozenset(Marker(value) for value in values) for x, y, values in data["markers"]
        },
        places={(x, y): _decode_place(center, corners) for x, y, center, corners in data["places"]},
        panel=_decode_panel(data["panel"]),
        enemy_panel=_decode_panel(data["enemy_panel"]),
        tap_mark=None
        if tap_mark is None
        else TapMarkReading(
            _pair(tap_mark["cell"]),
            None
            if tap_mark["terrain"] is None
            else tuple(Terrain(terrain) for terrain in tap_mark["terrain"]),
        ),
    )
    phase = data["phase"]
    return MapReadingRecord(
        _decode_still(data["still"]),
        reading,
        None if phase is None else Phase(phase),
        data["turn"],
    )


def encode_belief(belief: Belief) -> Json:
    """Return the parts of the belief that a plan of the survey reads."""
    ui = belief.ui
    return {
        "screen": ui.screen.value,
        "stack": [
            [group.group, None if group.caller is None else group.caller.value]
            for group in ui.stack
        ],
        "auto": None if ui.auto is None else ui.auto.value,
        "unit_list": None if ui.unit_list is None else ui.unit_list.value,
        "as_of": None if belief.as_of is None else _encode_still(belief.as_of),
    }


def decode_ui(data: Json) -> tuple[UiState, StillWindow | None]:
    ui = UiState(
        UiScreen(data["screen"]),
        tuple(
            OpenGroup(group, None if caller is None else UiScreen(caller))
            for group, caller in data["stack"]
        ),
        None if data["auto"] is None else UiAutoMode(data["auto"]),
        None if data["unit_list"] is None else UiUnitList(data["unit_list"]),
    )
    as_of = data["as_of"]
    return ui, None if as_of is None else _decode_still(as_of)


def encode_gesture(gesture: object) -> Json | None:
    match gesture:
        case None:
            return None
        case Tap(point):
            return {"kind": "tap", "point": list(point)}
        case Swipe(start, end, duration):
            return {"kind": "swipe", "start": list(start), "end": list(end), "duration": duration}
        case MapTap(cell):
            return {"kind": "map_tap", "cell": list(cell)}
        case Key(code):
            return {"kind": "key", "code": code}
        case _:
            raise TypeError(f"no JSON form for the gesture {gesture!r}")


def _encode_still(still: StillWindow) -> Json:
    return {"since": still.since, "until": still.until, "frame_seq": still.frame_seq}


def _decode_still(data: Json) -> StillWindow:
    return StillWindow(data["since"], data["until"], data["frame_seq"])


def _pair(values: list[int]) -> tuple[int, int]:
    first, second = values
    return first, second


def _decode_place(center: list[int], corners: list[list[int]]) -> CellPlace:
    first, second, third, fourth = (_pair(corner) for corner in corners)
    return CellPlace(_pair(center), (first, second, third, fourth))


def _encode_panel(panel: UnitPanel | None) -> Json | None:
    if panel is None:
        return None
    mech, pilot = panel.mech, panel.pilot
    return {
        "mech": {
            "icon": None if mech.icon is None else mech.icon.value,
            "name": _encode_name(mech.name),
            "hp": mech.hp,
            "en": mech.en,
            "hp_change": mech.hp_change,
            "en_change": mech.en_change,
            "overlay": mech.overlay,
        },
        "pilot": {
            "icon": None if pilot.icon is None else pilot.icon.value,
            "name": _encode_name(pilot.name),
            "mp": pilot.mp,
            "mp_max": pilot.mp_max,
            "state": None if pilot.state is None else pilot.state.value,
            "damage": pilot.damage,
            "chance_step": pilot.chance_step,
        },
    }


def _decode_panel(data: Json | None) -> UnitPanel | None:
    if data is None:
        return None
    mech, pilot = data["mech"], data["pilot"]
    return UnitPanel(
        MechPanel(
            None if mech["icon"] is None else PanelIcon(mech["icon"]),
            _decode_name(mech["name"]),
            mech["hp"],
            mech["en"],
            mech["hp_change"],
            mech["en_change"],
            mech["overlay"],
        ),
        PilotPanel(
            None if pilot["icon"] is None else PanelIcon(pilot["icon"]),
            _decode_name(pilot["name"]),
            pilot["mp"],
            pilot["mp_max"],
            None if pilot["state"] is None else PilotState(pilot["state"]),
            pilot["damage"],
            pilot["chance_step"],
        ),
    )


def _encode_name(name: NameTemplate | None) -> Json | None:
    if name is None:
        return None
    mask = name.mask
    return {
        "shape": list(mask.shape),
        "dtype": mask.dtype.str,
        "data": base64.b64encode(np.ascontiguousarray(mask).tobytes()).decode(),
    }


def _decode_name(data: Json | None) -> NameTemplate | None:
    if data is None:
        return None
    raw = base64.b64decode(data["data"])
    shape: list[int] = data["shape"]
    mask: np.ndarray = np.frombuffer(raw, dtype=np.dtype(data["dtype"]))
    return NameTemplate(mask.reshape(shape).copy())
