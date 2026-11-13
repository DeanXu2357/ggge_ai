import functools

import pytest

from ggge_ai_2.interpreter.elements.detectors import DETECTORS
from ggge_ai_2.mapparser.contract import Rect, ScreenPoint
from ggge_ai_2.mapparser.units import covered
from ggge_ai_2.screenmodel.contract import ModelElement, SeenElement
from ggge_ai_2.screenmodel.definition_model import DefinitionScreenModel
from tests.ggge_ai_2.dataset import Case, cases, load_image
from tests.ggge_ai_2.unit.mapparser.test_lattice import GRID_CASES

MODEL = DefinitionScreenModel()

MENU_BUTTON = (2170, 56)
TURN_BOX = (300, 60)
MAP_MIDDLE = (1170, 540)
END_TURN = (295, 185)
PROMPT = (400, 770)
UNIT_LIST = (1980, 765)
SECOND_CARD = (472, 900)
BACK = (1805, 970)
ACTION = (2060, 918)
SWITCH_UNIT = (230, 930)
INFO_PANEL = (1870, 410)
PREP_BANNER = (1170, 170)
PREP_PILOTS = (960, 950)
# The card row closes, so the prompt and the unit list button move down by 235 px.
CLOSED_PROMPT = (400, 1005)
CLOSED_UNIT_LIST = (1980, 1000)

SHOWN: dict[str, tuple[ScreenPoint, ...]] = {
    "player_phase_overview": (END_TURN, PROMPT, UNIT_LIST, SECOND_CARD),
    "select_action_in_battle": (BACK, ACTION, SWITCH_UNIT),
    "select_skill_in_battle": (BACK, ACTION, INFO_PANEL),
    "select_weapon_in_battle": (BACK, ACTION, INFO_PANEL),
    "select_weapon_in_battle_response": (BACK, ACTION, INFO_PANEL),
    "battle_prep_attack": (ACTION, PREP_PILOTS),
    "battle_prep_response_attack": (ACTION, PREP_PILOTS),
}
HIDDEN: dict[str, tuple[ScreenPoint, ...]] = {
    "player_phase_overview": (ACTION, INFO_PANEL, PREP_BANNER),
    "select_action_in_battle": (END_TURN, SECOND_CARD, INFO_PANEL, PREP_BANNER),
    "select_skill_in_battle": (SECOND_CARD, PREP_BANNER),
    "select_weapon_in_battle": (SECOND_CARD, PREP_BANNER),
    "select_weapon_in_battle_response": (SECOND_CARD, PREP_BANNER),
    "battle_prep_attack": (SECOND_CARD,),
    "battle_prep_response_attack": (SECOND_CARD,),
}
CLOSED_SHOWN = (END_TURN, CLOSED_PROMPT, CLOSED_UNIT_LIST)
CLOSED_HIDDEN = (PROMPT, UNIT_LIST, SECOND_CARD, ACTION, INFO_PANEL, PREP_BANNER)
# Only a card row of 11 cards reaches ACTION (roadmap section 8.10). These frames show
# 11 cards.
ELEVEN_CARDS = frozenset(f"map20261112-{index}" for index in range(26, 31))


@functools.cache
def _elements(case_id: str) -> tuple[SeenElement, ...]:
    image = load_image(next(case for case in cases() if case.id == case_id))
    return tuple(found for detector in DETECTORS for found in detector.detect(image))


def _occlusion(case: Case) -> tuple[Rect, ...]:
    return MODEL.judge(_elements(case.id)).occlusion


def _points(case: Case) -> tuple[tuple[ScreenPoint, ...], tuple[ScreenPoint, ...]]:
    if case.elements.get("unit_list") == "closed":
        return CLOSED_SHOWN, CLOSED_HIDDEN
    shown, hidden = SHOWN[case.screen], HIDDEN[case.screen]
    if case.id in ELEVEN_CARDS:
        return (*shown, ACTION), tuple(point for point in hidden if point != ACTION)
    return shown, hidden


# The parser reads no map in the phases of the other factions, so their HUD is not checked.
PANEL_CASES = [case for case in GRID_CASES if case.screen in SHOWN]


@pytest.mark.parametrize("case", PANEL_CASES, ids=[case.id for case in PANEL_CASES])
def test_covers_the_panels_of_the_labeled_screen(case: Case) -> None:
    rects = _occlusion(case)
    shown, hidden = _points(case)

    for point in (MENU_BUTTON, TURN_BOX, *shown):
        assert covered(point, rects), point
    for point in (MAP_MIDDLE, *hidden):
        assert not covered(point, rects), point


# On the battle prep screens, the attack banner shows between the unit panels. While the
# player chooses a support action, the banner is gone and the description panel shows.
PREP_PANELS = {
    "rec20261014-648": ((PREP_BANNER,), (INFO_PANEL,)),
    "rec20261014-882": ((PREP_BANNER,), (INFO_PANEL,)),
    "rec20261014-1079": ((INFO_PANEL,), (PREP_BANNER,)),
}
PREP_CASES = [case for case in cases() if case.id in PREP_PANELS]


@pytest.mark.parametrize("case", PREP_CASES, ids=[case.id for case in PREP_CASES])
def test_covers_the_banner_or_the_description_panel_on_battle_prep(case: Case) -> None:
    rects = _occlusion(case)
    shown, hidden = PREP_PANELS[case.id]

    assert all(covered(point, rects) for point in shown)
    assert not any(covered(point, rects) for point in hidden)


BATTLE_HUD = frozenset(
    {
        ModelElement.MENU_KEY,
        ModelElement.END_TURN_BUTTON,
        ModelElement.CHANGE_DEPLOY_BUTTON,
        ModelElement.PROMPT,
        ModelElement.UNIT_CARD,
        ModelElement.BACK_BUTTON,
        ModelElement.STANDBY_BUTTON,
        ModelElement.SKILL_BUTTON,
        ModelElement.SWITCH_TARGET_BUTTON,
        ModelElement.SWITCH_UNIT_ARROWS,
        ModelElement.CHOICE_BUTTON,
        ModelElement.PILOT_ROW,
        ModelElement.LEFT_UNIT_PANEL,
        ModelElement.RIGHT_UNIT_PANEL,
        ModelElement.ATTACK_BANNER,
        ModelElement.DESCRIPTION_PANEL,
    }
)
NO_HUD_CASES = [case for case in cases() if case.screen == "battle_main_setting"]


@pytest.mark.parametrize("case", NO_HUD_CASES, ids=[case.id for case in NO_HUD_CASES])
def test_finds_no_battle_hud_on_a_menu_without_the_battle_hud(case: Case) -> None:
    assert not {found.element for found in _elements(case.id)} & BATTLE_HUD
