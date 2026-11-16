from __future__ import annotations

from collections import defaultdict
from dataclasses import fields

from ggge_ai_2.mapgeom import contract as geo
from ggge_ai_2.mapgeom.stitch import same_name
from ggge_ai_2.stagedata.contract import (
    Faction,
    NameMask,
    PilotState,
    StageCell,
    StageData,
    StageUnit,
    UnitBrief,
    UnitDetail,
    UnitRole,
)


def stage_data(
    judgment: geo.MapJudgment, stage: str, app_version: str, code_version: str
) -> StageData:
    columns, rows = judgment.columns.size(), judgment.rows.size()
    assert columns is not None and rows is not None, "a finished survey closes both axes"
    unit_cells: defaultdict[geo.UnitId, list[geo.MapCell]] = defaultdict(list)
    for cell, unit_id in judgment.unit_cells.items():
        unit_cells[unit_id].append(cell)
    units: list[StageUnit] = []
    for unit_id, unit in judgment.units.items():
        assert unit.controllable is not None, "a finished survey knows the control of each unit"
        if unit.controllable:
            continue
        xs = [x for x, _ in unit_cells[unit_id]]
        ys = [y for _, y in unit_cells[unit_id]]
        # mapgeom takes a faction only from the left panel, and the left panel shows an
        # enemy. So a unit that the player does not control and that no left panel showed
        # is an NPC ally.
        faction = Faction.ENEMY if unit.faction is geo.Faction.ENEMY else Faction.ALLY
        units.append(
            StageUnit(
                (min(xs), min(ys)),
                (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1),
                faction,
                False,
                _brief(unit.brief),
                UnitDetail(),
            )
        )
    return StageData(
        stage=stage,
        app_version=app_version,
        code_version=code_version,
        columns=columns,
        rows=rows,
        terrain={},
        deploy_cells=(),
        units=tuple(sorted(units, key=lambda unit: _reading_order(unit.pos))),
        victory=(),
        events=(),
    )


def differences(stored: StageData, surveyed: StageData) -> tuple[str, ...]:
    """Return one line for each fact of the stored data that the survey does not repeat.

    The code version is not compared: it records the code, not the stage.
    """
    found = [
        f"{name}: {getattr(stored, name)} -> {getattr(surveyed, name)}"
        for name in ("columns", "rows", "deploy_cells")
        if getattr(stored, name) != getattr(surveyed, name)
    ]
    if stored.terrain != surveyed.terrain:
        found.append("terrain differs")
    old_units = {unit.pos: unit for unit in stored.units}
    new_units = {unit.pos: unit for unit in surveyed.units}
    for pos in sorted(old_units.keys() | new_units.keys(), key=_reading_order):
        old, new = old_units.get(pos), new_units.get(pos)
        if new is None:
            found.append(f"unit {pos}: missing")
        elif old is None:
            found.append(f"unit {pos}: new")
        else:
            found.extend(f"unit {pos}: {line}" for line in _unit_differences(old, new))
    return tuple(found)


def _unit_differences(old: StageUnit, new: StageUnit) -> list[str]:
    found = [
        f"{name} {getattr(old, name)} -> {getattr(new, name)}"
        for name in ("size", "faction", "controllable")
        if getattr(old, name) != getattr(new, name)
    ]
    for item in fields(UnitBrief):
        before, after = getattr(old.brief, item.name), getattr(new.brief, item.name)
        if isinstance(before, NameMask) and isinstance(after, NameMask):
            if not same_name(geo.NameMask(before.mask), geo.NameMask(after.mask)):
                found.append(f"{item.name} differs")
        elif before != after:
            found.append(f"{item.name} {before} -> {after}")
    return found


def _reading_order(cell: StageCell) -> tuple[int, int]:
    return cell[1], cell[0]


def _brief(brief: geo.UnitBrief | None) -> UnitBrief:
    assert (
        brief is not None
        and brief.mech_role is not None
        and brief.mech_name is not None
        and brief.hp is not None
        and brief.en is not None
        and brief.pilot_role is not None
        and brief.pilot_name is not None
        and brief.mp is not None
        and brief.mp_max is not None
        and brief.state is not None
    ), "a finished survey has the whole brief of each unit that the player does not control"
    return UnitBrief(
        mech_role=UnitRole(brief.mech_role.value),
        mech_name=NameMask(brief.mech_name.mask),
        hp=brief.hp,
        en=brief.en,
        pilot_role=UnitRole(brief.pilot_role.value),
        pilot_name=NameMask(brief.pilot_name.mask),
        mp=brief.mp,
        mp_max=brief.mp_max,
        state=PilotState(brief.state.value),
    )
