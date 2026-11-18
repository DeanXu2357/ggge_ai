import pytest

from ggge_ai_2.interpreter.elements.unit_list import UnitListButton, unit_list, unit_list_scores
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("unit_list") is not None]


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_unit_list_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    assert unit_list(image) is UnitListButton(case.elements["unit_list"]), unit_list_scores(image)
