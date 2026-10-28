import pytest

from ggge_ai_2.interpreter.contract import Phase
from ggge_ai_2.interpreter.phase_cue import PHASE_SCREENS, phase
from tests.ggge_ai_2.dataset import Case, cases, load_image

BAND_CASES = [case for case in cases() if case.screen in {screen.value for screen in PHASE_SCREENS}]


@pytest.mark.parametrize("case", BAND_CASES, ids=[case.id for case in BAND_CASES])
def test_phase_reads_the_labeled_phase(case: Case) -> None:
    assert phase(load_image(case)) == (None if case.phase is None else Phase(case.phase))
