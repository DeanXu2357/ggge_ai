"""FrameReading: what the classifier says about one screenshot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tag:
    """One UI feature layered on the screen, with the geometry the classifier found.

    `point` is part of the contract, not a debugging extra: the classifier is
    the one who located the button, so the reflex handler taps `tag.point`
    instead of scanning the frame a second time (floating-position rule).
    """

    name: str
    point: tuple[int, int] | None = None
    score: float = 1.0


@dataclass(frozen=True)
class FrameReading:
    """Every feature the classifier detected on one frame.

    Screen identity is a detection like any other, so it gets no channel of
    its own: which tags are identities (hub, unit panel, end-turn dialog) and
    which are overlays (skip buttons, popups, grid lines, tab markers) is
    registered in the symbol table, not encoded in this type. The two routers
    consume this in parallel; nothing else reads frames.
    """

    tags: tuple[Tag, ...] = ()

    def tag(self, name: str) -> Tag | None:
        for tag in self.tags:
            if tag.name == name:
                return tag
        return None

    def has(self, name: str) -> bool:
        return self.tag(name) is not None
