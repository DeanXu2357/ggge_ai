from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np

from ggge_ai_2.stream.contract import Frame

ScreenPoint = tuple[int, int]
# A cell is (column, row) of a map cell that the frame shows whole and that no element
# covers. (0, 0) is the top-left corner of the box around these cells.
ViewCell = tuple[int, int]


class Screen(StrEnum):
    STAGE_CHOSEN = "stage_chosen"
    SERIES_LIST = "series_list"
    SERIES_STAGE_INFO = "series_stage_info"
    STORY_STAGE_LIST = "story_stage_list"
    SORTIE_PREP = "sortie_prep"
    BATTLE_INFO_PREVIEW = "battle_info_preview"
    PLAYER_PHASE_OVERVIEW = "player_phase_overview"
    SELECT_ACTION_IN_BATTLE = "select_action_in_battle"
    SELECT_WEAPON_IN_BATTLE = "select_weapon_in_battle"
    SELECT_WEAPON_IN_BATTLE_RESPONSE = "select_weapon_in_battle_response"
    SELECT_WEAPON_IN_ATTACK_PREPARE = "select_weapon_in_attack_prepare"
    BATTLE_PREP_ATTACK = "battle_prep_attack"
    BATTLE_PREP_RESPONSE_ATTACK = "battle_prep_response_attack"
    NON_PLAYER_PHASE_BATTLE_VIEW = "non_player_phase_battle_view"
    BATTLE_MAIN_SETTING = "battle_main_setting"
    CHALLENGE_BATTLE_CHECK = "challenge_battle_check"
    BATTLE_SCORE_RESULT = "battle_score_result"
    EXP_REWARD_RESULT = "exp_reward_result"
    DROP_REWARD_RESULT = "drop_reward_result"
    POWER_SAVE_LOCK = "power_save_lock"
    POWER_SAVE_DIM = "power_save_dim"
    LOADING = "loading"
    SIMPLIFY_WEAPON_ANIME = "simplify_weapon_anime"
    EX_WEAPON_ANIME = "ex_weapon_anime"
    BATTLE_CLEAR_VIEW = "battle_clear_view"
    MAP_PASSING = "map_passing"
    UNIT_DETAIL_SUMMARY = "unit_detail_summary"


class Phase(StrEnum):
    PLAYER = "player"
    NON_PLAYER = "non_player"


class AutoMode(StrEnum):
    FULL = "full"
    SEMI = "semi"
    MANUAL = "manual"


class UnitList(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class SeenCell(StrEnum):
    OCCUPIED = "occupied"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


class SeenEdge(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


class SeenMarker(StrEnum):
    MOVE_RANGE = "move_range"
    THREAT = "threat"
    WEAPON_RANGE = "weapon_range"
    ENEMY_MOVE_RANGE = "enemy_move_range"


@dataclass(frozen=True)
class SeenUnit:
    # The anchor is the cell of the footprint with the least column and the least row,
    # as 'pos' in the battle engine. A unit cut by the frame edge can have its anchor
    # outside the frame.
    pos: ViewCell
    size: tuple[int, int]
    # None when the screen does not draw the chevrons, or the frame does not show the place
    # of the chevron above the unit.
    controllable: bool | None
    selected: bool
    enemy_selected: bool
    # True when a cell of the footprint is not a readable cell: an element or the frame edge
    # cuts the unit.
    cropped: bool


class SeenPanelIcon(StrEnum):
    RED = "red"
    BLUE = "blue"
    YELLOW = "yellow"
    GRAY = "gray"


class SeenPilotState(StrEnum):
    NORMAL = "一般"
    STRONG = "強勢"
    SUPER_STRONG = "超強勢"
    SUPER_STRIKE = "超一擊"


# The white mask of a name, cut to the box around its white pixels. Two crops of one name
# differ in some pixels, so compare two names by their similarity. Equality is identity.
@dataclass(frozen=True, eq=False)
class SeenName:
    mask: np.ndarray


@dataclass(frozen=True)
class SeenMechPanel:
    icon: SeenPanelIcon | None
    # The name as the panel shows it, cut with '…' when it is long.
    name: SeenName | None
    hp: int | None
    en: int | None
    hp_change: int | None
    en_change: int | None
    overlay: str | None


@dataclass(frozen=True)
class SeenPilotPanel:
    icon: SeenPanelIcon | None
    name: SeenName | None
    mp: int | None
    mp_max: int | None
    state: SeenPilotState | None
    damage: int | None
    chance_step: int | None


@dataclass(frozen=True)
class SeenUnitPanel:
    mech: SeenMechPanel
    pilot: SeenPilotPanel


class SeenTerrain(StrEnum):
    AIR = "air"
    GROUND = "ground"
    SPACE = "space"
    SURFACE = "surface"
    UNDERWATER = "underwater"


# The mark that a tap on an empty cell leaves: a fill on the cell and a terrain box above it.
@dataclass(frozen=True)
class SeenTapMark:
    cell: ViewCell
    # The icons of the terrain box from left to right. None when the box is outside the frame.
    terrain: tuple[SeenTerrain, ...] | None


@dataclass(frozen=True)
class SeenCellPlace:
    center: ScreenPoint
    # Top left, top right, bottom right, bottom left. The camera tilts down, so a cell is a
    # trapezoid on the screen.
    corners: tuple[ScreenPoint, ScreenPoint, ScreenPoint, ScreenPoint]


@dataclass(frozen=True)
class SeenMap:
    cells: Mapping[ViewCell, SeenCell]
    borders: frozenset[SeenEdge]
    units: tuple[SeenUnit, ...]
    markers: Mapping[ViewCell, frozenset[SeenMarker]]
    # The place on the screen of each readable cell in this frame.
    places: Mapping[ViewCell, SeenCellPlace]
    # The panel of the selected unit at the top right.
    panel: SeenUnitPanel | None
    # The panel of the selected enemy at the top left.
    enemy_panel: SeenUnitPanel | None
    tap_mark: SeenTapMark | None


@dataclass(frozen=True)
class Situation:
    frame_seq: int
    screen: Screen
    auto: AutoMode | None = None
    phase: Phase | None = None
    unit_list: UnitList | None = None
    turn: int | None = None
    map: SeenMap | None = None


class Interpreter(Protocol):
    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        """Return None when no screen is close enough to the frame.

        The candidates are the screens that the agent expects next. The interpreter can
        still return a screen outside the candidates, and the agent records it as a model
        mismatch.

        Do not return the closest screen when it is below the threshold. A popup that
        has no model then reads as a known screen, and the planner cannot stop on it.
        """
        ...
