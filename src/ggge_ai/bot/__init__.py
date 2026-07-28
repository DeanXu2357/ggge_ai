"""bot: the rewritten flow layer. Spec: docs/bot-architecture.md.

One tick = one screenshot, at most one device interaction, no idle ticks.
Classifier tags -> router (reflex table / symbol table) -> pure symbolic
actions on a persistent queue, replan as the only recovery.
"""

from .action import Action, Goal
from .board import BOARD_SYMBOLS, MockBoard
from .bot import Bot, BotStuck, TickRecord
from .frame import FrameReading, Tag
from .mocks import IdentityClassifier, MockClock, MockDevice, MockScreen
from .router import (
    ReflexRouter,
    ReflexRule,
    ReflexTable,
    SymbolTable,
    from_identity,
    identity_scope,
    misrouted_identity_tags,
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
    "IdentityClassifier",
    "MockBoard",
    "MockClock",
    "MockDevice",
    "MockScreen",
    "ReflexRouter",
    "ReflexRule",
    "ReflexTable",
    "SymbolTable",
    "Tag",
    "TickRecord",
    "from_identity",
    "identity_scope",
    "misrouted_identity_tags",
    "tag_present",
    "tag_value",
    "unproduced_symbols",
]
