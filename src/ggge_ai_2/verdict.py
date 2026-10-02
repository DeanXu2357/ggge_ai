from enum import StrEnum


class Verdict(StrEnum):
    HOLDS = "holds"
    DOES_NOT_HOLD = "does_not_hold"
    UNREADABLE = "unreadable"
