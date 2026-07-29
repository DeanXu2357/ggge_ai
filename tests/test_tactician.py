"""TacticalAdvisor：情報不全就不背書、計價出自沙盤搜尋、KILL 只給必殺。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from ggge_ai.contracts import HiddenPolicy, Objective, StageOrder
from ggge_ai.sandbox.advise import Guarantee, Verdict
from ggge_ai.sandbox.model import DEFAULT_RULES, legal_attacks, step
from ggge_ai.sandbox.search import SearchConfig, eval_bounds, solve
from ggge_ai.sandbox.tactician import TacticalAdvisor, TacticianConfig
from ggge_ai.stage.actions import Action, Attack, Brace, Inspect, Move, Standby, Withdraw
from ggge_ai.stage.goals import Annihilation
from ggge_ai.stage.intel import IntelPerceiver, Intelligence, Side, UnitIntel, WeaponIntel
from ggge_ai.stage.loop import StageLoop
from ggge_ai.stage.planner import Plan, plan
from ggge_ai.stage.run import stage_journal
from ggge_ai.stage.state import Phase, Reaction
from tests.fixtures.stage_offline import ScriptedPerceiver, battle, frame

RIFLE = WeaponIntel(name="rifle", power=100.0, range_min=1, range_max=2)
GUN = WeaponIntel(name="gun", power=50.0, range_min=1, range_max=1)
CONFIG = TacticianConfig(search=SearchConfig(max_depth=2, time_budget_s=30.0))
POSITIONS = {"a1": (0, 0), "e1": (1, 0), "e2": (2, 0)}


def ally(unit_id: str = "a1") -> UnitIntel:
    return UnitIntel(
        unit_id=unit_id,
        max_hp=1000,
        en_max=100,
        unit_attack=3000.0,
        unit_defense=1000.0,
        pilot_attack=1000.0,
        mobility=1000.0,
        move_range=3,
        weapons=(RIFLE,),
    )


def foe(unit_id: str, *, reaction: float = 0.0, max_hp: int = 200, guards: int = 0) -> UnitIntel:
    return UnitIntel(
        unit_id=unit_id,
        max_hp=max_hp,
        en_max=50,
        unit_attack=1000.0,
        unit_defense=1000.0,
        reaction=reaction,
        move_range=1,
        weapons=(GUN,),
        support_defend_charges_max=guards,
    )


def store(*, allies=(), enemies=(), priors=()) -> Intelligence:
    intel = Intelligence()
    for record in allies:
        intel.learn(record, Side.ROSTER)
    for record in enemies:
        intel.learn(record, Side.STAGE)
    for record in priors:
        intel.assume(record, Side.STAGE)
    return intel


def board_of(intel: Intelligence, state, config: TacticianConfig = CONFIG):
    advisor = TacticalAdvisor(intel, config=config)
    return advisor, advisor.board(state)


def full_knowledge(*foes: UnitIntel):
    intel = store(allies=[ally()], enemies=list(foes))
    names = [record.unit_id for record in foes]
    state = battle(
        allies=["a1"],
        enemies=names,
        positions={name: POSITIONS[name] for name in ("a1", *names)},
        known=["a1", *names],
    )
    return intel, state


def priced(advisor: TacticalAdvisor, state, action: Action):
    return advisor.price(state, (action,))[0]


def test_an_unknown_enemy_freezes_every_combat_candidate_but_not_the_scouting():
    intel = store(allies=[ally()], priors=[foe("e1"), foe("e2")])
    state = battle(
        allies=["a1"], enemies=["e1", "e2"], positions=POSITIONS, known=["a1"]
    )
    advisor = TacticalAdvisor(intel, config=CONFIG)
    options = (Attack("a1", "e1"), Standby("a1"), Inspect("e1"), Withdraw())

    prices = advisor.price(state, options)

    assert prices[0] is None
    assert prices[1] is None
    assert prices[2].cost == pytest.approx(CONFIG.inspect_cost)
    assert prices[3].cost == pytest.approx(CONFIG.withdraw_cost)
    assert all(pricing is None or pricing.guarantee is Guarantee.NONE for pricing in prices)


def test_a_missing_roster_record_freezes_combat_with_no_in_stage_remedy():
    intel = store(enemies=[foe("e1")])
    state = battle(allies=["a1"], enemies=["e1"], positions=POSITIONS, known=["a1", "e1"])
    advisor = TacticalAdvisor(intel, config=CONFIG)

    assert advisor.board(state) is None
    assert priced(advisor, state, Attack("a1", "e1")) is None


def test_a_unit_the_screen_never_placed_is_as_good_as_unknown():
    intel, state = full_knowledge(foe("e1"))
    advisor = TacticalAdvisor(intel, config=CONFIG)
    unplaced = replace(state, positions=frozenset({("a1", (0, 0))}))

    assert advisor.board(unplaced) is None
    assert priced(advisor, unplaced, Attack("a1", "e1")) is None


def test_the_price_of_an_attack_is_the_searchs_own_number():
    intel, state = full_knowledge(foe("e1"))
    advisor = TacticalAdvisor(intel, config=CONFIG)
    board = advisor.board(state)
    options = legal_attacks(board, board.unit("a1"))
    assert len(options) == 1

    pricing = priced(advisor, state, Attack("a1", "e1"))

    after = step(board, options[0], rules=DEFAULT_RULES)
    config = replace(advisor.search_config, objective=advisor.objective(board))
    value = solve(after, advisor.enemy_model, config).value
    _, vmax = eval_bounds(1, 1, advisor.search_config.weights)
    assert pricing.cost == pytest.approx(max(0.0, vmax - value))
    assert pricing.note == "rifle"


def test_a_kill_is_promised_only_when_the_dice_cannot_save_the_target():
    intel, state = full_knowledge(foe("e1"))
    advisor = TacticalAdvisor(intel, config=CONFIG)

    assert priced(advisor, state, Attack("a1", "e1")).guarantee is Guarantee.KILL


def test_a_hit_rate_short_of_the_threshold_gives_up_the_kill_promise():
    intel, state = full_knowledge(foe("e1", reaction=600.0))
    strict = TacticalAdvisor(intel, config=CONFIG)
    lenient = TacticalAdvisor(intel, config=replace(CONFIG, kill_hit_threshold=0.99))

    assert priced(strict, state, Attack("a1", "e1")).guarantee is Guarantee.NONE
    assert priced(lenient, state, Attack("a1", "e1")).guarantee is Guarantee.KILL


def test_a_target_that_survives_the_hardest_defence_is_no_guaranteed_kill():
    intel, state = full_knowledge(foe("e1", max_hp=10_000))
    advisor = TacticalAdvisor(intel, config=CONFIG)

    assert priced(advisor, state, Attack("a1", "e1")).guarantee is Guarantee.NONE


def test_an_interceptable_target_is_no_guaranteed_kill():
    intel, state = full_knowledge(foe("e1"), foe("e2", guards=1))
    advisor = TacticalAdvisor(intel, config=CONFIG)

    assert priced(advisor, state, Attack("a1", "e1")).guarantee is Guarantee.NONE
    assert priced(advisor, state, Attack("a1", "e2")).guarantee is Guarantee.KILL


def test_a_move_the_sandbox_cannot_walk_is_not_endorsed():
    intel, state = full_knowledge(foe("e1"))
    reachable = replace(state, reachable=frozenset({("a1", (1, 1)), ("a1", (40, 40))}))
    advisor = TacticalAdvisor(intel, config=CONFIG)

    assert priced(advisor, reachable, Move("a1", (1, 1))) is not None
    assert priced(advisor, reachable, Move("a1", (40, 40))) is None


def test_a_stance_on_screen_is_priced_and_an_unheard_of_one_is_not():
    intel = store(allies=[ally()], enemies=[foe("e1")])
    popup = Reaction(defender="a1", attacker="e1", stances=("dodge", "shrug"))
    state = battle(
        allies=["a1"],
        enemies=["e1"],
        actionable=[],
        phase=Phase.ENEMY,
        positions=POSITIONS,
        known=["a1", "e1"],
        reaction=popup,
    )
    advisor = TacticalAdvisor(intel, config=CONFIG)

    dodge = priced(advisor, state, Brace("a1", "e1", "dodge"))

    assert dodge is not None
    assert dodge.guarantee is Guarantee.NONE
    assert priced(advisor, state, Brace("a1", "e1", "shrug")) is None


def test_appraise_stays_the_course_while_the_board_is_still_unread():
    intel = store(allies=[ally()], priors=[foe("e1")])
    state = battle(allies=["a1"], enemies=["e1"], positions=POSITIONS, known=["a1"])

    verdict = TacticalAdvisor(intel, config=CONFIG).appraise(state)

    assert verdict.verdict is Verdict.PURSUE


def test_appraise_cuts_the_losses_once_the_leaf_score_falls_below_the_threshold():
    intel, state = full_knowledge(foe("e1"), foe("e2"))
    quitter = TacticalAdvisor(intel, config=replace(CONFIG, withdraw_below=0.0))
    stayer = TacticalAdvisor(intel, config=replace(CONFIG, withdraw_below=-5.0))

    assert quitter.appraise(state).verdict is Verdict.WITHDRAW
    assert stayer.appraise(state).verdict is Verdict.PURSUE
    assert TacticalAdvisor(intel, config=CONFIG).appraise(state).verdict is Verdict.PURSUE


def test_the_plan_scouts_both_unknown_enemies_before_it_opens_fire():
    intel = store(allies=[ally()], priors=[foe("e1"), foe("e2")])
    state = battle(
        allies=["a1"], enemies=["e1", "e2"], positions=POSITIONS, known=["a1"]
    )

    result = plan(state, Annihilation(), TacticalAdvisor(intel, config=CONFIG))

    assert isinstance(result, Plan)
    labels = [step.action.label for step in result.steps]
    assert sorted(labels[:2]) == ["inspect:e1", "inspect:e2"]
    assert labels[2].startswith("attack:a1->")
    assert result.steps[2].pricing.guarantee is Guarantee.KILL
    assert result.truncated


@dataclass
class ScoutingExecutor:
    """站 2c 解析器的位子：Inspect 落地就把面板寫回情報庫。"""

    intel: Intelligence
    panels: dict[str, UnitIntel]
    performed: list[Action] = field(default_factory=list)

    def perform(self, action: Action, observation) -> None:
        self.performed.append(action)
        if isinstance(action, Inspect):
            self.intel.learn(self.panels[action.target], Side.STAGE)

    @property
    def labels(self) -> list[str]:
        return [action.label for action in self.performed]


def test_the_loop_scouts_then_attacks_as_the_store_fills(tmp_path):
    panels = {"e1": foe("e1"), "e2": foe("e2")}
    intel = store(allies=[ally()], priors=list(panels.values()))
    unread = battle(
        allies=["a1"], enemies=["e1", "e2"], positions=POSITIONS, known=[]
    )
    executor = ScoutingExecutor(intel, panels)
    loop = StageLoop(
        StageOrder(
            stage="unicorn-hard-1",
            objectives=frozenset({Objective.CLEAR}),
            hidden_policy=HiddenPolicy.DECLINE,
            max_ticks=10,
        ),
        perceiver=IntelPerceiver(ScriptedPerceiver([frame(unread)]), intel),
        executor=executor,
        advisor=TacticalAdvisor(intel, config=CONFIG),
        victory=Annihilation(),
        journal=stage_journal(tmp_path),
    )

    for _ in range(3):
        loop.tick()

    assert sorted(executor.labels[:2]) == ["inspect:e1", "inspect:e2"]
    assert executor.labels[2].startswith("attack:a1->")
    assert intel.known("e1") and intel.known("e2")
