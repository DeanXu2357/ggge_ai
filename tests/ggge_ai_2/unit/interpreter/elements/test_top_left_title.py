import pytest

from ggge_ai_2.interpreter.elements.top_left_title import (
    TopLeftTitle,
    title_ious,
    top_left_title,
)
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("top_left_title") is not None]
BATTLE_TITLES = {title.value for title in TopLeftTitle}


def _expected(case: Case) -> TopLeftTitle | None:
    ruling = case.elements["top_left_title"]
    return TopLeftTitle(ruling) if ruling in BATTLE_TITLES else None


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_top_left_title_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    assert top_left_title(image) is _expected(case), {
        "ruling": case.elements["top_left_title"],
        **{title.value: round(iou, 3) for title, iou in title_ious(image).items()},
    }
