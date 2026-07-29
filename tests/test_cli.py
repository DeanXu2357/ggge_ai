"""CLI 解析：goal 輸入轉成 GoalSpec，run 目錄可注入。"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from ggge_ai.cli import build_parser, goal_from_args, main, parse_objectives, resolve_run_dir
from ggge_ai.contracts import Constraint, Objective


def _parse(*argv: str):
    return build_parser().parse_args(argv)


def test_defaults_are_clear_and_split():
    goal = goal_from_args(_parse("--stage", "demo"))

    assert goal.stage == "demo"
    assert goal.objectives == frozenset({Objective.CLEAR})
    assert goal.constraint is Constraint.SPLIT


def test_objectives_accept_a_comma_separated_subset():
    goal = goal_from_args(_parse("--stage", "demo", "--objectives", "clear,hidden"))

    assert goal.objectives == frozenset({Objective.CLEAR, Objective.HIDDEN})


def test_constraint_single_is_accepted():
    goal = goal_from_args(_parse("--stage", "demo", "--constraint", "single"))

    assert goal.constraint is Constraint.SINGLE


@pytest.mark.parametrize("text", ["", " , ", "clear,quest"])
def test_bad_objectives_are_rejected(text):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_objectives(text)


def test_unknown_objective_fails_the_parser():
    with pytest.raises(SystemExit):
        _parse("--stage", "demo", "--objectives", "quest")


def test_stage_is_required():
    with pytest.raises(SystemExit):
        _parse("--objectives", "clear")


def test_batch_zero_refuses_a_live_run(tmp_path):
    with pytest.raises(SystemExit):
        main(["--stage", "demo", "--run-dir", str(tmp_path / "run")])


def test_run_dir_defaults_under_the_injected_runs_root(tmp_path):
    resolved = resolve_run_dir(None, runs_root=tmp_path / "runs")

    assert resolved.parent == tmp_path / "runs"
    assert resolve_run_dir(str(tmp_path / "explicit")) == Path(tmp_path / "explicit")
