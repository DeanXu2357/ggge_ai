from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ggge_ai_2.interpreter.contract import (
    Phase,
    Screen,
    SeenCell,
    SeenCellPlace,
    SeenEdge,
    SeenMap,
    SeenMarker,
    SeenMechPanel,
    SeenPanelIcon,
    SeenPilotPanel,
    SeenPilotState,
    SeenTapMark,
    SeenTerrain,
    SeenUnit,
    SeenUnitPanel,
)
from ggge_ai_2.interpreter.element_first import ElementFirstInterpreter
from ggge_ai_2.mapparser.contract import (
    CellPlace,
    CellReading,
    Edge,
    MapReading,
    MapScope,
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
from ggge_ai_2.screenmodel.contract import (
    MapRequest,
    ModelElement,
    ModelPhase,
    ModelScreen,
    ScreenJudgment,
    SeenElement,
)
from ggge_ai_2.stream.contract import Frame

FRAME = Frame(np.zeros((1080, 2340, 3), np.uint8), captured_at=1.0, seq=7)
TURN = SeenElement(ModelElement.TURN_BOX, "3", (150, 5, 800, 112))
TITLE = SeenElement(ModelElement.TOP_LEFT_TITLE, "player_phase", (160, 30, 600, 60))
BAND = SeenElement(ModelElement.TITLE_BAND, "player", (160, 30, 600, 60))
OVERVIEW = ScreenJudgment(
    ModelScreen.PLAYER_PHASE_OVERVIEW,
    frozenset({ModelScreen.PLAYER_PHASE_OVERVIEW}),
    ModelPhase.NON_PLAYER,
    3,
    ((150, 5, 800, 112), (195, 960, 1240, 1020)),
    MapRequest(chevrons=True),
)
EMPTY_READING = MapReading({}, frozenset(), (), {}, {}, None, None)


@dataclass
class FakeDetector:
    found: tuple[SeenElement, ...]

    def detect(self, image: np.ndarray) -> Sequence[SeenElement]:
        return self.found


@dataclass
class MockScreenModel:
    judgment: ScreenJudgment
    given: list[list[SeenElement]] = field(default_factory=list[list[SeenElement]])

    def judge(self, elements: Sequence[SeenElement]) -> ScreenJudgment:
        self.given.append(list(elements))
        return self.judgment


@dataclass
class MockMapParser:
    reading: MapReading | None
    scopes: list[MapScope] = field(default_factory=list[MapScope])

    def parse(self, frame: Frame, scope: MapScope) -> MapReading | None:
        self.scopes.append(scope)
        return self.reading


def _interpreter(
    model: MockScreenModel, parser: MockMapParser | None = None
) -> ElementFirstInterpreter:
    return ElementFirstInterpreter(
        (FakeDetector((TURN, TITLE)), FakeDetector(()), FakeDetector((BAND,))),
        model,
        parser or MockMapParser(EMPTY_READING),
    )


def test_hands_the_elements_of_every_detector_to_the_screen_model() -> None:
    model = MockScreenModel(OVERVIEW)

    _interpreter(model).interpret(FRAME, frozenset())

    assert model.given == [[TURN, TITLE, BAND]]


def test_gives_the_screen_the_phase_and_the_turn_of_the_judgment() -> None:
    situation = _interpreter(MockScreenModel(OVERVIEW)).interpret(FRAME, frozenset())

    assert situation is not None
    assert (situation.frame_seq, situation.screen, situation.phase, situation.turn) == (
        7,
        Screen.PLAYER_PHASE_OVERVIEW,
        Phase.NON_PLAYER,
        3,
    )


def test_gives_no_situation_and_reads_no_map_when_the_screen_model_judges_no_screen() -> None:
    parser = MockMapParser(EMPTY_READING)
    undecided = ScreenJudgment(
        None,
        frozenset({ModelScreen.BATTLE_PREP_ATTACK, ModelScreen.SELECT_WEAPON_IN_ATTACK_PREPARE}),
        None,
        None,
        (),
        None,
    )

    assert _interpreter(MockScreenModel(undecided), parser).interpret(FRAME, frozenset()) is None
    assert parser.scopes == []


def test_reads_the_map_in_the_scope_that_the_screen_model_gives() -> None:
    parser = MockMapParser(EMPTY_READING)

    situation = _interpreter(MockScreenModel(OVERVIEW), parser).interpret(FRAME, frozenset())

    assert parser.scopes == [MapScope(((150, 5, 800, 112), (195, 960, 1240, 1020)), True)]
    assert situation is not None and situation.map is not None


def test_reads_no_map_when_the_screen_model_asks_for_none() -> None:
    parser = MockMapParser(EMPTY_READING)
    prep = ScreenJudgment(
        ModelScreen.BATTLE_PREP_ATTACK,
        frozenset({ModelScreen.BATTLE_PREP_ATTACK}),
        ModelPhase.PLAYER,
        3,
        (),
        None,
    )

    situation = _interpreter(MockScreenModel(prep), parser).interpret(FRAME, frozenset())

    assert parser.scopes == []
    assert situation is not None and situation.map is None


def test_converts_every_field_of_the_map_reading() -> None:
    corners = ((660, 370), (742, 370), (746, 432), (655, 432))
    mech = MechPanel(PanelIcon.RED, None, 20000, 20, -1500, None, "KILL")
    pilot = PilotPanel(PanelIcon.BLUE, None, 0, 12, PilotState.STRONG, 300, 1)
    enemy_mech = MechPanel(PanelIcon.YELLOW, None, 9000, None, None, None, None)
    enemy_pilot = PilotPanel(PanelIcon.GRAY, None, None, None, None, None, None)
    reading = MapReading(
        cells={(0, 0): CellReading.OCCUPIED, (1, 0): CellReading.UNREADABLE},
        borders=frozenset({Edge.TOP}),
        units=(UnitReading((0, 0), (1, 1), True, False, True, cropped=True),),
        markers={(1, 0): frozenset({Marker.ENEMY_MOVE_RANGE})},
        places={(0, 0): CellPlace((700, 400), corners)},
        panel=UnitPanel(mech, pilot),
        enemy_panel=UnitPanel(enemy_mech, enemy_pilot),
        tap_mark=TapMarkReading((1, 0), (Terrain.AIR, Terrain.SPACE)),
    )

    situation = _interpreter(MockScreenModel(OVERVIEW), MockMapParser(reading)).interpret(
        FRAME, frozenset()
    )

    assert situation is not None
    assert situation.map == SeenMap(
        cells={(0, 0): SeenCell.OCCUPIED, (1, 0): SeenCell.UNREADABLE},
        borders=frozenset({SeenEdge.TOP}),
        units=(SeenUnit((0, 0), (1, 1), True, False, True, True),),
        markers={(1, 0): frozenset({SeenMarker.ENEMY_MOVE_RANGE})},
        places={(0, 0): SeenCellPlace((700, 400), corners)},
        panel=SeenUnitPanel(
            SeenMechPanel(SeenPanelIcon.RED, None, 20000, 20, -1500, None, "KILL"),
            SeenPilotPanel(SeenPanelIcon.BLUE, None, 0, 12, SeenPilotState.STRONG, 300, 1),
        ),
        enemy_panel=SeenUnitPanel(
            SeenMechPanel(SeenPanelIcon.YELLOW, None, 9000, None, None, None, None),
            SeenPilotPanel(SeenPanelIcon.GRAY, None, None, None, None, None, None),
        ),
        tap_mark=SeenTapMark((1, 0), (SeenTerrain.AIR, SeenTerrain.SPACE)),
    )


def test_keeps_the_mask_of_each_name_on_the_panels() -> None:
    mech_name, pilot_name = np.ones((14, 60), np.uint8), np.zeros((14, 40), np.uint8)
    panel = UnitPanel(
        MechPanel(None, NameTemplate(mech_name), None, None, None, None, None),
        PilotPanel(None, NameTemplate(pilot_name), None, None, None, None, None),
    )
    reading = MapReading({}, frozenset(), (), {}, {}, None, panel)

    situation = _interpreter(MockScreenModel(OVERVIEW), MockMapParser(reading)).interpret(
        FRAME, frozenset()
    )

    assert situation is not None and situation.map is not None
    enemy = situation.map.enemy_panel
    assert enemy is not None and enemy.mech.name is not None and enemy.pilot.name is not None
    assert enemy.mech.name.mask is mech_name
    assert enemy.pilot.name.mask is pilot_name
