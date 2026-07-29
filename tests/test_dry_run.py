"""dry-run 端到端：假帳本同步 → HTN 無適用方法 → 誠實停止報告落檔。"""

from __future__ import annotations

import json

from ggge_ai.cli import main


def _run(tmp_path):
    run_dir = tmp_path / "run"
    argv = ["--stage", "demo", "--objectives", "clear", "--dry-run", "--run-dir", str(run_dir)]
    return main(argv), run_dir


def test_dry_run_stops_honestly_and_files_a_report(tmp_path):
    code, run_dir = _run(tmp_path)

    assert code == 0
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["kind"] == "no_applicable_method"
    assert report["detail"]["task"] == "achieve_goal"
    assert report["detail"]["tried"] == ["clear_by_sortie"]
    assert "no applicable method" in report["reason"]
    assert report["goal"] == {"stage": "demo", "objectives": ["clear"], "constraint": "split"}
    assert report["state"] == {"ledger_synced": True}
    assert report["dry_run"] is True
    assert report["journal"] == "strategy.jsonl"


def test_dry_run_leaves_a_journal_of_the_whole_lifecycle(tmp_path):
    _, run_dir = _run(tmp_path)

    lines = [
        json.loads(line)
        for line in (run_dir / "strategy.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [line["kind"] for line in lines] == ["run_start", "ledger_sync", "htn_root", "stop"]
    assert [line["seq"] for line in lines] == [0, 1, 2, 3]
    assert lines[0]["objectives"] == ["clear"]
    assert lines[1]["synced"] is True
    assert lines[2]["task"] == "achieve_goal"
    assert lines[3]["stop_kind"] == "no_applicable_method"
    assert lines[3]["detail"]["tried"] == ["clear_by_sortie"]


def test_dry_run_prints_the_stop_reason(tmp_path, capsys):
    _, run_dir = _run(tmp_path)

    out = capsys.readouterr().out
    assert "no_applicable_method" in out
    assert str(run_dir) in out


def test_single_constraint_round_trips_into_the_report(tmp_path):
    run_dir = tmp_path / "single"
    main(
        [
            "--stage",
            "S01",
            "--objectives",
            "clear,score",
            "--constraint",
            "single",
            "--dry-run",
            "--run-dir",
            str(run_dir),
        ]
    )

    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["goal"] == {
        "stage": "S01",
        "objectives": ["clear", "score"],
        "constraint": "single",
    }
