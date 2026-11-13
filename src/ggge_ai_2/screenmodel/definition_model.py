from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ggge_ai_2.screenmodel.contract import (
    ModelElement,
    ModelPhase,
    ScreenJudgment,
    SeenElement,
)
from ggge_ai_2.screenmodel.definition import ScreenDefinition
from ggge_ai_2.screenmodel.screens import DEFINITIONS


@dataclass(frozen=True)
class DefinitionScreenModel:
    definitions: tuple[ScreenDefinition, ...] = DEFINITIONS

    def judge(self, elements: Sequence[SeenElement]) -> ScreenJudgment:
        matched = [definition for definition in self.definitions if definition.matches(elements)]
        found = matched[0] if len(matched) == 1 else None
        return ScreenJudgment(
            screen=None if found is None else found.screen,
            matched=frozenset(definition.screen for definition in matched),
            phase=_phase(elements) if found is not None and found.phase else None,
            turn=None if found is None else _turn(elements),
            occlusion=tuple(seen.box for seen in elements),
            map=None if found is None else found.map,
        )


def _content(elements: Sequence[SeenElement], element: ModelElement) -> str | None:
    return next(
        (seen.content for seen in elements if seen.element is element and seen.content is not None),
        None,
    )


def _phase(elements: Sequence[SeenElement]) -> ModelPhase | None:
    content = _content(elements, ModelElement.TITLE_BAND)
    return None if content is None else ModelPhase(content)


def _turn(elements: Sequence[SeenElement]) -> int | None:
    content = _content(elements, ModelElement.TURN_BOX)
    return None if content is None else int(content)
