"""行動詞彙：保守下界的效果，以及機械展開的候選集。"""

from __future__ import annotations

import pytest

from ggge_ai.sandbox.advise import Guarantee, Pricing
from ggge_ai.stage.actions import (
    VOCABULARY,
    Attack,
    Brace,
    Inspect,
    Move,
    ShowGrid,
    Standby,
    SurveyBoard,
    Withdraw,
    candidates,
)
from ggge_ai.stage.state import Phase, Reaction, StageState, next_player_phase
from tests.fixtures.stage_offline import battle

FREE = Pricing(1.0)
LETHAL = Pricing(1.0, Guarantee.KILL)


def test_the_vocabulary_is_exactly_these_verbs():
    assert VOCABULARY == (
        Move,
        Attack,
        Inspect,
        ShowGrid,
        SurveyBoard,
        Standby,
        Brace,
        Withdraw,
    )


def test_an_attack_without_a_kill_guarantee_leaves_the_enemy_alive():
    state = battle(allies=["a1"], enemies=["e1"])

    after = Attack("a1", "e1").apply(state, FREE)

    assert after.enemies == {"e1"}
    assert after.actionable == frozenset()


def test_only_a_kill_guarantee_removes_the_enemy():
    state = battle(allies=["a1"], enemies=["e1", "e2"])

    after = Attack("a1", "e1").apply(state, LETHAL)

    assert after.enemies == {"e2"}


def test_an_attack_counts_as_progress_once_the_unit_has_spent_its_turn():
    action = Attack("a1", "e1")
    spent = battle(allies=["a1"], enemies=["e1"], actionable=[])

    assert action.progressed(spent, FREE)
    assert not action.progressed(spent, LETHAL)
    assert action.progressed(battle(allies=["a1"], enemies=[], actionable=[]), LETHAL)


def test_an_attack_is_not_progress_while_the_unit_is_still_actionable():
    assert not Attack("a1", "e1").progressed(battle(allies=["a1"], enemies=["e1"]), FREE)


def test_a_move_needs_the_destination_to_be_in_the_perceived_reach():
    state = battle(allies=["a1"], enemies=["e1"], reachable={"a1": [(2, 3)]})

    assert Move("a1", (2, 3)).applicable(state)
    assert not Move("a1", (9, 9)).applicable(state)


def test_a_move_relocates_the_unit_and_ends_its_action():
    state = battle(
        allies=["a1"], enemies=["e1"], positions={"a1": (0, 0)}, reachable={"a1": [(2, 3)]}
    )

    after = Move("a1", (2, 3)).apply(state, FREE)

    assert after.position_of("a1") == (2, 3)
    assert after.actionable == frozenset()
    assert Move("a1", (2, 3)).progressed(after, FREE)
    assert not Move("a1", (9, 9)).progressed(after, FREE)


def test_standby_only_spends_the_unit():
    state = battle(allies=["a1", "a2"], enemies=["e1"])

    after = Standby("a1").apply(state, FREE)

    assert after.actionable == {"a2"}
    assert after.enemies == {"e1"}


def test_brace_needs_the_popup_and_promises_nothing_but_answering_it():
    reaction = Reaction(defender="a1", attacker="e1", stances=("dodge", "defend"))
    state = battle(allies=["a1"], enemies=["e1"], phase=Phase.ENEMY, reaction=reaction)

    assert Brace("a1", "e1", "dodge").applicable(state)
    assert not Brace("a1", "e1", "counter").applicable(state)
    assert not Brace("a1", "e1", "dodge").applicable(battle(allies=["a1"], enemies=["e1"]))

    after = Brace("a1", "e1", "dodge").apply(state, FREE)
    assert after.reaction is None
    assert after.allies == {"a1"}
    assert after.enemies == {"e1"}


def test_withdraw_marks_the_plan_side_leave_flag():
    state = battle(allies=["a1"], enemies=["e1"])

    after = Withdraw().apply(state, FREE)

    assert after.withdrawn
    assert not Withdraw().applicable(after)
    assert Withdraw().progressed(after, FREE)


def test_candidates_expand_every_unit_against_every_enemy_and_every_reachable_cell():
    state = battle(
        allies=["a1", "a2"],
        enemies=["e1", "e2"],
        actionable=["a1"],
        reachable={"a1": [(1, 1), (1, 2)]},
    )

    labels = [action.label for action in candidates(state)]

    assert labels == [
        "standby:a1",
        "attack:a1->e1",
        "attack:a1->e2",
        "move:a1->1,1",
        "move:a1->1,2",
        "withdraw",
    ]


def test_inspect_needs_a_live_unknown_target_and_only_buys_intel():
    state = battle(allies=["a1"], enemies=["e1", "e2"], known=["a1", "e2"])

    assert Inspect("e1").applicable(state)
    assert not Inspect("e2").applicable(state)
    assert not Inspect("ghost").applicable(state)

    after = Inspect("e1").apply(state, FREE)

    assert after.known == {"a1", "e1", "e2"}
    assert after.actionable == {"a1"}
    assert after.enemies == {"e1", "e2"}
    assert Inspect("e1").progressed(after, FREE)
    assert not Inspect("e1").progressed(state, FREE)


def test_inspect_is_off_the_table_during_the_enemy_phase():
    state = battle(allies=["a1"], enemies=["e1"], actionable=[], phase=Phase.ENEMY, known=["a1"])

    assert not Inspect("e1").applicable(state)


def test_candidates_expand_inspect_for_every_unknown_enemy():
    state = battle(allies=["a1"], enemies=["e1", "e2"], known=["a1", "e1"])

    labels = [action.label for action in candidates(state)]

    assert labels == ["standby:a1", "attack:a1->e1", "attack:a1->e2", "inspect:e2", "withdraw"]


def test_candidates_during_a_popup_are_only_the_stances_on_screen():
    reaction = Reaction(defender="a1", attacker="e1", stances=("dodge", "defend"))
    state = battle(allies=["a1"], enemies=["e1"], phase=Phase.ENEMY, reaction=reaction)

    assert [action.label for action in candidates(state)] == [
        "brace:a1<-e1:dodge",
        "brace:a1<-e1:defend",
    ]


def test_the_enemy_phase_offers_nothing_to_plan():
    state = battle(allies=["a1"], enemies=["e1"], actionable=[], phase=Phase.ENEMY)

    assert candidates(state) == ()


def test_the_phase_boundary_restores_the_survivors_and_nothing_else():
    state = battle(allies=["a1", "a2"], enemies=["e1"], actionable=[])

    after = next_player_phase(state)

    assert after.actionable == {"a1", "a2"}
    assert after.enemies == {"e1"}
    assert after.phase is Phase.PLAYER


def test_a_state_cannot_declare_a_unit_actionable_that_is_not_alive():
    with pytest.raises(ValueError):
        StageState(
            phase=Phase.PLAYER,
            allies=frozenset({"a1"}),
            actionable=frozenset({"a1", "ghost"}),
            enemies=frozenset(),
        )
