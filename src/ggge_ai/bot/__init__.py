"""bot: the rewritten flow layer. Spec: docs/bot-architecture.md.

One tick = one screenshot, at most one device interaction, no idle ticks.
Classifier {phase, tags} -> router (reflex table / symbol table) -> pure
symbolic actions on a persistent queue, replan as the only recovery.
"""

from .action import Action, Goal
from .board import BOARD_SYMBOLS, MockBoard
from .bot import Bot, BotStuck, TickRecord
from .frame import FrameReading, Tag
from .mocks import MockClassifier, MockClock, MockDevice
from .router import (
    ReflexRule,
    ReflexTable,
    SymbolTable,
    from_phase,
    on_phases,
    tag_present,
    tag_value,
    unproduced_symbols,
)
from .state import UNKNOWN, BotState

__all__ = [
    "BOARD_SYMBOLS",
    "UNKNOWN",
    "Action",
    "Bot",
    "BotStuck",
    "BotState",
    "FrameReading",
    "Goal",
    "MockBoard",
    "MockClassifier",
    "MockClock",
    "MockDevice",
    "ReflexRule",
    "ReflexTable",
    "SymbolTable",
    "Tag",
    "TickRecord",
    "from_phase",
    "on_phases",
    "tag_present",
    "tag_value",
    "unproduced_symbols",
]
