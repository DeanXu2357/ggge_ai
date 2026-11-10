import pytest

from ggge_ai_2.mapparser.unit_panel import (
    ENEMY,
    SELECTED,
    PanelLayout,
    has_panel,
    panel_line_peaks,
    read_panel,
)
from tests.ggge_ai_2.dataset import Case, cases, load_image

LAYOUTS: dict[str, PanelLayout] = {"unit_panel": SELECTED, "enemy_panel": ENEMY}
RULED = [
    (element, case)
    for element in LAYOUTS
    for case in cases()
    if case.elements.get(element) is not None
]


@pytest.mark.parametrize(
    ("element", "case"), RULED, ids=[f"{element}-{case.id}" for element, case in RULED]
)
def test_panel_matches_the_ruling(element: str, case: Case) -> None:
    image = load_image(case)
    layout = LAYOUTS[element]

    assert has_panel(image, layout) is (case.elements[element] == "present"), (
        f"ruling={case.elements[element]} peaks={panel_line_peaks(image, layout)}"
    )


def _ruled_panel(element: str, case: Case) -> dict[str, dict[str, object]] | None:
    return case.unit_panel if element == "unit_panel" else case.enemy_panel


PANELS = [(element, case) for element, case in RULED if _ruled_panel(element, case) is not None]
READ_FIELDS = {
    "mech": ("icon", "name", "hp", "en", "hp_change", "en_change", "overlay"),
    "pilot": ("icon", "name", "mp", "mp_max", "state", "damage", "chance_step"),
}


@pytest.mark.parametrize(
    ("element", "case"), PANELS, ids=[f"{element}-{case.id}" for element, case in PANELS]
)
def test_panel_reads_the_ruled_fields(element: str, case: Case) -> None:
    ruling = _ruled_panel(element, case)
    assert ruling is not None
    panel = read_panel(load_image(case), LAYOUTS[element])

    assert panel is not None
    blocks = {"mech": panel.mech, "pilot": panel.pilot}
    read = {
        (block, field): getattr(blocks[block], field)
        for block, fields in READ_FIELDS.items()
        for field in fields
    }
    ruled = {
        (block, field): ruling[block][field]
        for block, fields in READ_FIELDS.items()
        for field in fields
    }
    assert {key: None if value is None else str(value) for key, value in read.items()} == {
        key: None if value is None else str(value) for key, value in ruled.items()
    }
