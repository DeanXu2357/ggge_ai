import pytest

from ggge_ai_2.mapparser.contract import ScreenPoint
from ggge_ai_2.mapparser.hud import covered, hud_cells, hud_rects
from ggge_ai_2.mapparser.lattice import read_lattice
from tests.ggge_ai_2.dataset import Case, cases, load_image
from tests.ggge_ai_2.unit.mapparser.test_lattice import GRID_CASES

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
    # With ten units, the card row reaches the point of the back button.
    "player_phase_overview": (ACTION, INFO_PANEL, PREP_BANNER),
    "select_action_in_battle": (END_TURN, SECOND_CARD, INFO_PANEL, PREP_BANNER),
    "select_skill_in_battle": (SECOND_CARD, PREP_BANNER),
    "select_weapon_in_battle": (SECOND_CARD, PREP_BANNER),
    "select_weapon_in_battle_response": (SECOND_CARD, PREP_BANNER),
    "battle_prep_attack": (SECOND_CARD,),
    "battle_prep_response_attack": (SECOND_CARD,),
}


# The parser reads no map in the phases of the other factions, so their HUD is not checked.
PANEL_CASES = [case for case in GRID_CASES if case.screen in SHOWN]


@pytest.mark.parametrize("case", PANEL_CASES, ids=[case.id for case in PANEL_CASES])
def test_covers_the_panels_of_the_labeled_screen(case: Case) -> None:
    rects = hud_rects(load_image(case))

    for point in (MENU_BUTTON, TURN_BOX, *SHOWN[case.screen]):
        assert covered(point, rects), point
    for point in (MAP_MIDDLE, *HIDDEN[case.screen]):
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
    rects = hud_rects(load_image(case))
    shown, hidden = PREP_PANELS[case.id]

    assert all(covered(point, rects) for point in shown)
    assert not any(covered(point, rects) for point in hidden)


NO_HUD_CASES = [case for case in cases() if case.screen == "battle_main_setting"]


@pytest.mark.parametrize("case", NO_HUD_CASES, ids=[case.id for case in NO_HUD_CASES])
def test_covers_nothing_on_a_menu_without_the_battle_hud(case: Case) -> None:
    assert hud_rects(load_image(case)) == ()


def test_hud_cells_are_the_cells_with_a_covered_center() -> None:
    image = load_image(GRID_CASES[0])
    lattice = read_lattice(image)
    assert lattice is not None
    rects = hud_rects(image)

    cells = hud_cells(image, lattice)

    assert cells
    assert cells == {cell for cell in lattice.cells() if covered(lattice.center(cell), rects)}
