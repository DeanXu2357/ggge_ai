from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ggge_ai_2.uisim.chart import AutoButton, Gesture, ScreenChart, Target, Transition
from ggge_ai_2.uisim.chart_data import CHART
from ggge_ai_2.uisim.contract import RatioRect, UiScreen
from ggge_ai_2.uisim.stages import ScreenDef, load_stages

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"
STAGES = load_stages(REAL_STAGES)
PASS_THROUGH_KINDS = frozenset({"animation", "loading"})
NODE_NAMES = frozenset(screen.value for screen in UiScreen)

ALLY = UiScreen.ROSTER_LIST_ALLY
ENEMY = UiScreen.ROSTER_LIST_ENEMY
BATTLE_DETAIL = tuple(
    Target(screen, "unit_detail")
    for screen in (
        UiScreen.UNIT_DETAIL_STATE,
        UiScreen.UNIT_DETAIL_ACTION,
        UiScreen.UNIT_DETAIL_ABILITY,
        UiScreen.UNIT_DETAIL_SUMMARY,
    )
)
ROSTER_DETAIL = tuple(
    Target(UiScreen(f"{target.screen}_roster"), "unit_detail") for target in BATTLE_DETAIL
)
TO_MENU = (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),)
UNIT_ICON_SCREENS = (
    UiScreen.SELECT_ACTION_IN_BATTLE,
    UiScreen.SELECT_WEAPON_IN_BATTLE,
    UiScreen.BATTLE_PREP_ATTACK,
    UiScreen.BATTLE_PREP_RESPONSE_ATTACK,
)

# The ally roster takes the buttons and rects of 'roster_list': recording 20261014-234132 has
# only the ally tab (#545).
SPLIT_SOURCES = {ALLY: "roster_list"}
REPLACED_TARGETS: dict[str, tuple[Target, ...]] = {
    # The discovery graph of recording 20261014-234132 has these moves: #544 -> #545 and
    # #545 -> #547.
    "battle_main_setting__squad_info": (Target(ALLY),),
    "roster_list_ally__mech_card": ROSTER_DETAIL,
    # The graph has no frames for these moves. They follow the user rulings and the
    # 'unit_detail' group note.
    "roster_list_ally__tab_enemy": (Target(ENEMY),),
    "roster_list_ally__close": TO_MENU,
    **{f"{target.screen}__close": (Target(ALLY), Target(ENEMY)) for target in ROSTER_DETAIL},
    # Frames #515, #585, #769, #773 and #893 show the battle pages after a battle screen. The
    # '_roster' pages open from the roster list.
    **{
        f"{screen}__{icon}": BATTLE_DETAIL
        for screen in UNIT_ICON_SCREENS
        for icon in ("ally_unit_icon", "enemy_unit_icon")
    },
}
# The enemy tab has no frames. Its moves mirror the ally roster and have no rect.
ADDED_SCREENS = {
    ENEMY: ScreenChart(
        (
            Transition("roster_list_enemy__tab_ally", None, (Target(ALLY),), 15.0),
            Transition("roster_list_enemy__mech_card", None, ROSTER_DETAIL, 15.0),
            Transition("roster_list_enemy__close", None, TO_MENU, 15.0),
        )
    )
}
ADDED_MEMBERS = {"battle_menu": frozenset({ALLY, ENEMY})}
LEFT_OUT_GROUPS = frozenset({"unit_info"})


def _entry_group(name: str) -> str | None:
    groups = [group.name for group in STAGES.groups.values() if name in group.entry]
    return groups[0] if len(groups) == 1 else None


def _resolved(names: Sequence[str]) -> tuple[Target, ...]:
    resolved: list[Target] = []
    visited: set[str] = set()
    for name in names:
        _resolve(name, None, visited, resolved)
    return tuple(resolved)


def _resolve(name: str, group: str | None, visited: set[str], resolved: list[Target]) -> None:
    if name in visited:
        return
    visited.add(name)
    if "@" in name:
        group_name = name.split("@", 1)[0]
        stage_group = STAGES.groups.get(group_name)
        entries = (group_name,) if stage_group is None else stage_group.entry
        for entry in entries:
            _resolve(entry, None if stage_group is None else group_name, visited, resolved)
        return
    screen = STAGES.screens.get(name)
    if screen is not None and screen.kind in PASS_THROUGH_KINDS:
        for button in screen.buttons:
            for target in button.to:
                _resolve(target, None, visited, resolved)
        for target in screen.game_to:
            _resolve(target, None, visited, resolved)
        return
    if name in NODE_NAMES and all(target.screen != name for target in resolved):
        resolved.append(Target(UiScreen(name), _entry_group(name) if group is None else group))


def _expected_chart(node: UiScreen, screen: ScreenDef) -> tuple[ScreenChart, set[str]]:
    transitions: list[Transition] = []
    auto: AutoButton | None = None
    danger: list[RatioRect] = []
    names: set[str] = set()
    for button in screen.buttons:
        name = node.value + button.name.removeprefix(screen.name)
        names.add(name)
        if button.forbidden:
            danger.extend(() if button.rect is None else (button.rect,))
        elif name.endswith("__auto"):
            assert button.rect is not None
            auto = AutoButton(name, button.rect, button.deadline)
        elif targets := REPLACED_TARGETS.get(name, _resolved(button.to)):
            gesture = Gesture.TAP if button.gesture is None else Gesture(button.gesture)
            transitions.append(Transition(name, button.rect, targets, button.deadline, gesture))
    waits = _resolved(screen.game_to)
    return ScreenChart(tuple(transitions), auto, waits, tuple(danger)), names


def _stage_source(node: UiScreen) -> ScreenDef | None:
    return STAGES.screens.get(SPLIT_SOURCES.get(node, node.value))


def test_chart_defines_every_ui_screen() -> None:
    assert set(CHART.screens) == set(UiScreen)


def test_chart_screens_match_stages_json_with_the_listed_differences() -> None:
    seen: set[str] = set()
    drift: list[str] = []
    for node in UiScreen:
        source = _stage_source(node)
        if source is None:
            expected = ADDED_SCREENS[node]
        else:
            expected, names = _expected_chart(node, source)
            seen |= names
        if CHART.screens[node] != expected:
            drift.append(f"{node}: chart {CHART.screens[node]} != expected {expected}")

    assert drift == []
    assert REPLACED_TARGETS.keys() <= seen
    assert all(_stage_source(node) is None for node in ADDED_SCREENS)


def test_chart_groups_match_stages_json_with_the_listed_differences() -> None:
    expected = {
        name: (
            frozenset(UiScreen(screen) for screen in group.entry),
            frozenset(UiScreen(screen) for screen in (*group.entry, *group.inside))
            | ADDED_MEMBERS.get(name, frozenset()),
        )
        for name, group in STAGES.groups.items()
        if name not in LEFT_OUT_GROUPS
    }

    assert {group.name: (group.entry, group.members) for group in CHART.groups} == expected


def test_no_node_opens_the_left_out_groups() -> None:
    openers = [
        (screen.name, button.name)
        for screen in STAGES.screens.values()
        if screen.name in NODE_NAMES
        for button in screen.buttons
        for target in button.to
        if target.split("@", 1)[0] in LEFT_OUT_GROUPS or _entry_group(target) in LEFT_OUT_GROUPS
    ]

    assert openers == []


def test_every_named_group_of_a_target_is_a_chart_group() -> None:
    names = {group.name for group in CHART.groups}
    named = {
        target.group
        for screen in CHART.screens.values()
        for targets in (
            *(transition.targets for transition in screen.transitions),
            screen.waits,
        )
        for target in targets
        if target.group is not None
    }

    assert named <= names
