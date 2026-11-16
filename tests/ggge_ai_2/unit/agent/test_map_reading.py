import numpy as np

from ggge_ai_2.agent.map_reading import map_reading
from ggge_ai_2.interpreter.seen_map import seen_map
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


def test_a_map_reading_comes_back_whole_from_the_map_of_the_interpreter() -> None:
    reading = MapReading(
        cells={(0, 0): CellReading.OCCUPIED, (1, 0): CellReading.UNREADABLE},
        borders=frozenset({Edge.TOP, Edge.LEFT}),
        units=(UnitReading((0, 0), (2, 1), None, True, False, cropped=True),),
        markers={(1, 0): frozenset({Marker.MOVE_RANGE, Marker.THREAT})},
        places={(0, 0): CellPlace((700, 400), ((660, 370), (742, 370), (746, 432), (655, 432)))},
        panel=UnitPanel(
            MechPanel(PanelIcon.BLUE, None, 20000, 20, None, -5, None),
            PilotPanel(PanelIcon.BLUE, None, 3, 12, PilotState.SUPER_STRIKE, None, 2),
        ),
        enemy_panel=UnitPanel(
            MechPanel(PanelIcon.RED, None, 9000, 30, -1500, None, "KILL"),
            PilotPanel(PanelIcon.RED, None, 0, 10, PilotState.NORMAL, 300, None),
        ),
        tap_mark=TapMarkReading((1, 0), (Terrain.GROUND, Terrain.UNDERWATER)),
    )

    assert map_reading(seen_map(reading)) == reading


def test_the_masks_of_the_names_come_back_unchanged() -> None:
    mech_name, pilot_name = np.ones((14, 60), np.uint8), np.zeros((14, 40), np.uint8)
    panel = UnitPanel(
        MechPanel(None, NameTemplate(mech_name), None, None, None, None, None),
        PilotPanel(None, NameTemplate(pilot_name), None, None, None, None, None),
    )

    back = map_reading(seen_map(MapReading({}, frozenset(), (), {}, {}, panel, None))).panel

    assert back is not None and back.mech.name is not None and back.pilot.name is not None
    assert back.mech.name.mask is mech_name
    assert back.pilot.name.mask is pilot_name
