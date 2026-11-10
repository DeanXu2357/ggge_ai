import functools
import json

import cv2
import pytest

from ggge_ai_2.mapparser.contract import NameTemplate
from ggge_ai_2.mapparser.unit_panel import (
    ENEMY,
    SELECTED,
    PANEL_TEMPLATES,
    PanelLayout,
    has_panel,
    panel_line_peaks,
    read_panel,
    similarity,
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
    "mech": ("icon", "hp", "en", "hp_change", "en_change", "overlay"),
    "pilot": ("icon", "mp", "mp_max", "state", "damage", "chance_step"),
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
    assert {block: blocks[block].name is not None for block in blocks} == {
        block: ruling[block]["name"] is not None for block in blocks
    }


# Two crops of one name differ in size by a few pixels, so the smaller crop gets a margin
# and slides over the larger one.
NAME_SLACK = (4, 3)
SAME_NAME = 0.75


def _name_similarity(a: NameTemplate, b: NameTemplate) -> float:
    slack_x, slack_y = NAME_SLACK
    found, template = a.mask, b.mask
    if (
        abs(template.shape[1] - found.shape[1]) > slack_x
        or abs(template.shape[0] - found.shape[0]) > slack_y
    ):
        return 0.0
    padded = cv2.copyMakeBorder(
        found,
        slack_y,
        slack_y + max(0, template.shape[0] - found.shape[0]),
        slack_x,
        slack_x + max(0, template.shape[1] - found.shape[1]),
        cv2.BORDER_CONSTANT,
        value=0,
    )
    return similarity(padded, template)


@functools.cache
def _saved_names() -> tuple[tuple[str, str, NameTemplate], ...]:
    index: dict[str, str] = json.loads((PANEL_TEMPLATES / "names.json").read_text("utf-8"))
    saved: list[tuple[str, str, NameTemplate]] = []
    for file, name in index.items():
        mask = cv2.imread(str(PANEL_TEMPLATES / file), cv2.IMREAD_GRAYSCALE)
        assert mask is not None, file
        saved.append((file.split("_")[1], name, NameTemplate(mask)))
    return tuple(saved)


@pytest.mark.parametrize(
    ("element", "case"), PANELS, ids=[f"{element}-{case.id}" for element, case in PANELS]
)
def test_name_template_matches_only_the_saved_template_of_the_ruled_name(
    element: str, case: Case
) -> None:
    ruling = _ruled_panel(element, case)
    assert ruling is not None
    panel = read_panel(load_image(case), LAYOUTS[element])
    assert panel is not None

    for block, read in (("mech", panel.mech.name), ("pilot", panel.pilot.name)):
        if read is None:
            continue
        matched = sorted(
            name
            for kind, name, saved in _saved_names()
            if kind == block and _name_similarity(read, saved) >= SAME_NAME
        )
        assert matched == [ruling[block]["name"]], block
