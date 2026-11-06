import pytest

from ggge_ai_2.interpreter.elements.round_button import (
    RoundButton,
    round_button,
    round_ring_coverage,
    round_text_scores,
)
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("round_button") is not None]


def _expected(case: Case) -> RoundButton | None:
    ruling = case.elements["round_button"]
    return None if ruling == "absent" else RoundButton(ruling)


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_round_button_matches_the_ruling(case: Case) -> None:
    image = load_image(case)

    scores = {kind.value: round(score, 3) for kind, score in round_text_scores(image).items()}
    assert round_button(image) is _expected(case), (
        f"ruling={case.elements['round_button']} ring={round_ring_coverage(image):.3f} {scores}"
    )
