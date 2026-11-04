import pytest

from ggge_ai_2.interpreter.elements.menu_key import (
    menu_key_glyph_score,
    menu_key_lit,
    menu_key_white_share,
)
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("menu_key") is not None]


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_menu_key_lit_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    assert menu_key_lit(image) is (case.elements["menu_key"] == "lit"), (
        f"ruling={case.elements['menu_key']} white_share={menu_key_white_share(image):.3f}"
        f" glyph={menu_key_glyph_score(image):.3f}"
    )
