"""Definition file -> offline battle: the pure-simulation entry (M8-4)."""

from ggge_ai.battle import stage_sim
from ggge_ai.battle.actions import ActionKind
from ggge_ai.battle.enemy_model import NearestTargetPolicy
from ggge_ai.battle.sim import SimUnit, SimWeapon, step
from ggge_ai.battle.solver import SolverConfig, solve
from ggge_ai.battle.stage_def import (
    Condition,
    StageConditions,
    StageDefinition,
    StageEvent,
    StageUnit,
    assign_uids,
)
from ggge_ai.battle.state import Faction

SIG_A = "a" * 16


def _stats(hp=60, en=50):
    return dict(
        hp=hp, en=en, move_range=3, unit_attack=2000, unit_defense=1000,
        unit_mobility=1000, pilot_shooting=1500, pilot_melee=1500,
        pilot_awakening=100, pilot_defense=800, pilot_reaction=900, sp=10,
    )


def _weapon_row(power=1500):
    return dict(kind="shooting", level=1, range_min=1, range_max=4,
                power=power, en_cost=5, hit_pct=100, crit_pct=0)


def _defn():
    layout = assign_uids(
        [
            StageUnit(uid="", cell=(4, 0), sig=SIG_A, stats=_stats(),
                      weapons=[_weapon_row()]),
            StageUnit(uid="", cell=(6, 2), sig=SIG_A, stats=_stats(hp=90),
                      weapons=[_weapon_row()]),
        ]
    )
    events = [
        StageEvent(
            event_id="ev1",
            trigger={"type": "kill", "uid": "e01", "within_turn": 2},
            effect={
                "type": "spawn",
                "units": [
                    {
                        "uid": "e09",
                        "cell": [7, 0],
                        "sig": SIG_A,
                        "stats": _stats(hp=200),
                        "weapons": [_weapon_row(power=4000)],
                    }
                ],
            },
        )
    ]
    conditions = StageConditions(
        victory=[Condition(type="decapitate", params={"targets": ["e02"]})],
        defeat=[],
    )
    return StageDefinition(stage_id="t/sim", layout=layout,
                           conditions=conditions, events=events)


def _ally(pos=(0, 0)):
    return SimUnit(
        unit_id="ally_1", faction=Faction.ALLY, pos=pos, hp=100, max_hp=100,
        en=60, en_max=60, unit_attack=6000, pilot_attack=9000, move_range=4,
        weapons=[SimWeapon("rifle", power=9000, range_min=1, range_max=6)],
    )


def test_layout_opens_on_board_and_spawns_stay_off():
    state, table, objective, notes = stage_sim.to_sim_state(_defn(), [_ally()])
    ids = {u.unit_id for u in state.units}
    assert {"e01", "e02", "ally_1"} <= ids
    assert "e09" not in ids
    assert state.pending_events == ("ev1",)
    template = table["ev1"].effect["units"][0]
    assert isinstance(template, SimUnit)
    assert template.hp == 200
    e01 = state.unit("e01")
    assert e01.hp == 60
    assert e01.unit_attack == 2000.0


def test_spawn_template_lands_on_the_layout_grid():
    state, table, _, _ = stage_sim.to_sim_state(_defn(), [_ally()])
    e01 = state.unit("e01")
    template = table["ev1"].effect["units"][0]
    assert template.pos[0] - e01.pos[0] == 3
    assert template.pos[1] == e01.pos[1]


def test_kill_inside_window_spawns_the_reinforcement():
    state, table, _, _ = stage_sim.to_sim_state(_defn(), [_ally(pos=(3, 0))])
    from ggge_ai.battle.sim import Decision

    after = step(
        state,
        Decision(unit_id="ally_1", kind=ActionKind.ATTACK, target_id="e01",
                 weapon="rifle", hit=True),
        events=table,
    )
    assert after.unit("e09") is not None
    assert after.fired_events == ("ev1",)


def test_offline_solve_walks_to_the_decapitation_win():
    defn = _defn()
    state, table, objective, _ = stage_sim.to_sim_state(defn, [_ally(pos=(3, 1))])
    result = solve(
        state,
        NearestTargetPolicy(),
        SolverConfig(time_budget_s=5.0, max_depth=2, objective=objective,
                     events=table),
    )
    attacks = [d.target_id for d in result.pv if d.kind == ActionKind.ATTACK]
    assert attacks and attacks[0] == "e02"
    assert result.value == objective.bounds[1]


def test_fired_events_are_excluded_from_pending():
    state, table, _, _ = stage_sim.to_sim_state(
        _defn(), [_ally()], fired_events=("ev1",)
    )
    assert state.pending_events == ()
    assert state.fired_events == ("ev1",)
