from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ggge_ai_2.screenmodel.contract import MapRequest, ModelElement, ModelScreen, SeenElement


@dataclass(frozen=True)
class Need:
    element: ModelElement
    # None matches any content.
    content: str | None = None

    def met_by(self, seen: SeenElement) -> bool:
        return seen.element is self.element and (
            self.content is None or seen.content == self.content
        )


@dataclass(frozen=True)
class ScreenDefinition:
    screen: ModelScreen
    needs: tuple[Need, ...]
    # Other screens can show a blue or red area where the title band is, for example the
    # game title. So only the screens with the band give the phase.
    phase: bool = False
    auto: bool = False
    unit_list: bool = False
    map: MapRequest | None = None

    def matches(self, elements: Sequence[SeenElement]) -> bool:
        return all(any(need.met_by(seen) for seen in elements) for need in self.needs)
