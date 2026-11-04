import pytest

from ggge_ai_2.interpreter.elements.turn_box import has_turn_box, turn_box_white_share
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("turn_box") is not None]


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_turn_box_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    assert has_turn_box(image) is (case.elements["turn_box"] == "present"), (
        f"ruling={case.elements['turn_box']} white_share={turn_box_white_share(image):.3f}"
    )
