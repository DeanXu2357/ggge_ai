from __future__ import annotations

from ggge_ai_2.interpreter.contract import (
    SeenMap,
    SeenMechPanel,
    SeenName,
    SeenPanelIcon,
    SeenPilotPanel,
    SeenTapMark,
    SeenUnitPanel,
)
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


def map_reading(seen: SeenMap) -> MapReading:
    return MapReading(
        cells={cell: CellReading(value.value) for cell, value in seen.cells.items()},
        borders=frozenset(Edge(edge.value) for edge in seen.borders),
        units=tuple(
            UnitReading(
                unit.pos,
                unit.size,
                unit.controllable,
                unit.selected,
                unit.enemy_selected,
                unit.cropped,
            )
            for unit in seen.units
        ),
        markers={
            cell: frozenset(Marker(marker.value) for marker in markers)
            for cell, markers in seen.markers.items()
        },
        places={
            cell: CellPlace(place.center, place.corners) for cell, place in seen.places.items()
        },
        panel=_panel(seen.panel),
        enemy_panel=_panel(seen.enemy_panel),
        tap_mark=_tap_mark(seen.tap_mark),
    )


def _panel(panel: SeenUnitPanel | None) -> UnitPanel | None:
    if panel is None:
        return None
    return UnitPanel(_mech(panel.mech), _pilot(panel.pilot))


def _mech(mech: SeenMechPanel) -> MechPanel:
    return MechPanel(
        _icon(mech.icon),
        _name(mech.name),
        mech.hp,
        mech.en,
        mech.hp_change,
        mech.en_change,
        mech.overlay,
    )


def _pilot(pilot: SeenPilotPanel) -> PilotPanel:
    return PilotPanel(
        _icon(pilot.icon),
        _name(pilot.name),
        pilot.mp,
        pilot.mp_max,
        None if pilot.state is None else PilotState(pilot.state.value),
        pilot.damage,
        pilot.chance_step,
    )


def _icon(icon: SeenPanelIcon | None) -> PanelIcon | None:
    return None if icon is None else PanelIcon(icon.value)


def _name(name: SeenName | None) -> NameTemplate | None:
    return None if name is None else NameTemplate(name.mask)


def _tap_mark(mark: SeenTapMark | None) -> TapMarkReading | None:
    if mark is None:
        return None
    terrain = None if mark.terrain is None else tuple(Terrain(t.value) for t in mark.terrain)
    return TapMarkReading(mark.cell, terrain)
