import pytest

from ggge_ai_2.interpreter.elements.tap_to_next import has_tap_to_next, tap_to_next_score
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("tap_to_next") is not None]


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_tap_to_next_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    assert has_tap_to_next(image) is (case.elements["tap_to_next"] == "present"), (
        f"ruling={case.elements['tap_to_next']} score={tap_to_next_score(image):.3f}"
    )
