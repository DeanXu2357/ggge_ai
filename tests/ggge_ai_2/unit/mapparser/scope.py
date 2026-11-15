import functools

from ggge_ai_2.interpreter.elements.detectors import DETECTORS
from ggge_ai_2.mapparser.contract import MapScope
from ggge_ai_2.screenmodel.definition_model import DefinitionScreenModel
from tests.ggge_ai_2.dataset import Case, cases, load_image

MODEL = DefinitionScreenModel()


def scope_of(case: Case) -> MapScope:
    return _scope(case.id)


# Keyed by the case ID because a Case holds a dict and does not hash.
@functools.cache
def _scope(case_id: str) -> MapScope:
    image = load_image(next(case for case in cases() if case.id == case_id))
    judgment = MODEL.judge([found for detector in DETECTORS for found in detector.detect(image)])
    return MapScope(judgment.occlusion, judgment.map is not None and judgment.map.chevrons)
