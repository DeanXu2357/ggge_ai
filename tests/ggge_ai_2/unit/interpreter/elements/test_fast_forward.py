import pytest

from ggge_ai_2.interpreter.elements.fast_forward import (
    fast_forward_glyph_score,
    fast_forward_outline_coverage,
    has_fast_forward,
)
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("fast_forward") is not None]


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_fast_forward_presence_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    assert has_fast_forward(image) is (case.elements["fast_forward"] != "absent"), (
        f"ruling={case.elements['fast_forward']}"
        f" outline={fast_forward_outline_coverage(image):.3f}"
        f" glyph={fast_forward_glyph_score(image):.3f}"
    )
