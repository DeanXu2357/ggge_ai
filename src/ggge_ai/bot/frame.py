"""FrameReading: what the classifier says about one screenshot."""

from __future__ import annotations

from dataclasses import dataclass

from .state import UNKNOWN


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
    """Classifier output for one frame: a phase plus zero or more tags.

    `phase` is a closed enum of screens the flow deliberately visits --
    including every choice dialog -- or UNKNOWN. `tags` are overlay features
    (skip buttons, info popups, grid lines, active tab markers): an open set.
    The two routers consume this in parallel; nothing else reads frames.
    """

    phase: str = UNKNOWN
    tags: tuple[Tag, ...] = ()

    def tag(self, name: str) -> Tag | None:
        for tag in self.tags:
            if tag.name == name:
                return tag
        return None

    def has(self, name: str) -> bool:
        return self.tag(name) is not None

    def key(self) -> tuple[str, tuple[str, ...]]:
        """Refire fingerprint: same key = the screen has not visibly changed."""
        return (self.phase, tuple(sorted(tag.name for tag in self.tags)))
