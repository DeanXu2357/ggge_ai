import pytest

from ggge_ai.agent import blackboard


@pytest.fixture(autouse=True)
def _runs_root_in_tmp(tmp_path, monkeypatch):
    """Tests building a real RunBlackboard streamed ledgers into the actual
    data/runs/ tree (single stage_info lines that read like aborted live
    runs -- 2026-07-23 forensics); every suite run leaves ghosts there."""
    monkeypatch.setattr(blackboard, "RUNS_ROOT", tmp_path / "runs")
