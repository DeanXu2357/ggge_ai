from __future__ import annotations

from ggge_ai_2.interpreter.contract import (
    SeenCell,
    SeenCellPlace,
    SeenEdge,
    SeenMap,
    SeenMarker,
    SeenMechPanel,
    SeenName,
    SeenPanelIcon,
    SeenPilotPanel,
    SeenPilotState,
    SeenTapMark,
    SeenTerrain,
    SeenUnit,
    SeenUnitPanel,
)
from ggge_ai_2.mapparser.contract import (
    MapReading,
    MechPanel,
    NameTemplate,
    PanelIcon,
    PilotPanel,
    TapMarkReading,
    UnitPanel,
)


def seen_map(reading: MapReading) -> SeenMap:
    return SeenMap(
        cells={cell: SeenCell(value.value) for cell, value in reading.cells.items()},
        borders=frozenset(SeenEdge(edge.value) for edge in reading.borders),
        units=tuple(
            SeenUnit(
                unit.pos,
                unit.size,
                unit.controllable,
                unit.selected,
                unit.enemy_selected,
                unit.cropped,
            )
            for unit in reading.units
        ),
        markers={
            cell: frozenset(SeenMarker(marker.value) for marker in markers)
            for cell, markers in reading.markers.items()
        },
        places={
            cell: SeenCellPlace(place.center, place.corners)
            for cell, place in reading.places.items()
        },
        panel=_panel(reading.panel),
        enemy_panel=_panel(reading.enemy_panel),
        tap_mark=_tap_mark(reading.tap_mark),
    )


def _panel(panel: UnitPanel | None) -> SeenUnitPanel | None:
    if panel is None:
        return None
    return SeenUnitPanel(_mech(panel.mech), _pilot(panel.pilot))


def _mech(mech: MechPanel) -> SeenMechPanel:
    return SeenMechPanel(
        _icon(mech.icon),
        _name(mech.name),
        mech.hp,
        mech.en,
        mech.hp_change,
        mech.en_change,
        mech.overlay,
    )


def _pilot(pilot: PilotPanel) -> SeenPilotPanel:
    return SeenPilotPanel(
        _icon(pilot.icon),
        _name(pilot.name),
        pilot.mp,
        pilot.mp_max,
        None if pilot.state is None else SeenPilotState(pilot.state.value),
        pilot.damage,
        pilot.chance_step,
    )


def _icon(icon: PanelIcon | None) -> SeenPanelIcon | None:
    return None if icon is None else SeenPanelIcon(icon.value)


def _name(name: NameTemplate | None) -> SeenName | None:
    return None if name is None else SeenName(name.mask)


def _tap_mark(mark: TapMarkReading | None) -> SeenTapMark | None:
    if mark is None:
        return None
    terrain = None if mark.terrain is None else tuple(SeenTerrain(t.value) for t in mark.terrain)
    return SeenTapMark(mark.cell, terrain)
