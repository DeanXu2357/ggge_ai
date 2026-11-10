import pytest

from ggge_ai_2.mapparser.unit_panel import has_unit_panel, panel_line_peaks, read_unit_panel
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("unit_panel") is not None]


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_unit_panel_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    assert has_unit_panel(image) is (case.elements["unit_panel"] == "present"), (
        f"ruling={case.elements['unit_panel']} peaks={panel_line_peaks(image)}"
    )


PANELS = [case for case in RULED if case.unit_panel is not None]
READ_FIELDS = {
    "mech": ("icon", "name", "hp", "en", "hp_change", "en_change", "overlay"),
    "pilot": ("icon", "name", "mp", "mp_max", "state", "damage", "chance_step"),
}


@pytest.mark.parametrize("case", PANELS, ids=[case.id for case in PANELS])
def test_unit_panel_reads_the_ruled_fields(case: Case) -> None:
    assert case.unit_panel is not None
    panel = read_unit_panel(load_image(case))

    assert panel is not None
    blocks = {"mech": panel.mech, "pilot": panel.pilot}
    read = {
        (block, field): getattr(blocks[block], field)
        for block, fields in READ_FIELDS.items()
        for field in fields
    }
    ruled = {
        (block, field): case.unit_panel[block][field]
        for block, fields in READ_FIELDS.items()
        for field in fields
    }
    assert {key: None if value is None else str(value) for key, value in read.items()} == {
        key: None if value is None else str(value) for key, value in ruled.items()
    }
