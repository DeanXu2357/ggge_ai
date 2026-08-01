"""流水帳回放的純函式：run 來源解析、jsonl 選檔、壞行容忍、幀路徑防跳脫。

全程只碰 tmp_path 造的假 run，不起伺服器、不 bind port、不碰 adb。
"""

from __future__ import annotations

import json
import tarfile

import pytest

from scripts.replay_run import (
    find_journal,
    load_entries,
    resolve_run,
    safe_frame_path,
)

LINES = (
    {"seq": 0, "t": 0.738, "kind": "zoom_backend", "available": True},
    {"seq": 1, "t": 2.309, "kind": "frame", "frame": "frames/00000-tick0002.png"},
    {"seq": 2, "t": 5.398, "kind": "gate", "name": "select", "trail": ["stage_list:ok"]},
)


def make_run(root, name="20260801-212645", journal="dry_run.jsonl", lines=LINES):
    run_dir = root / name
    (run_dir / "frames").mkdir(parents=True)
    (run_dir / "frames" / "00000-tick0002.png").write_bytes(b"\x89PNG\r\n\x1a\n fake")
    body = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    (run_dir / journal).write_text(body, encoding="utf-8")
    return run_dir


def archive(run_dir, destination):
    bundle_path = destination / (run_dir.name + ".tar.gz")
    with tarfile.open(bundle_path, "w:gz") as bundle:
        bundle.add(run_dir, arcname=run_dir.name)
    return bundle_path


def test_resolve_run_takes_directory_path(tmp_path):
    run_dir = make_run(tmp_path / "runs")
    assert resolve_run(str(run_dir), tmp_path / "runs") == run_dir


def test_resolve_run_extracts_archive_path(tmp_path):
    runs_root = tmp_path / "runs"
    run_dir = make_run(runs_root)
    bundle = archive(run_dir, tmp_path)

    resolved = resolve_run(str(bundle), runs_root)

    assert resolved.name == run_dir.name
    assert resolved != run_dir
    assert (resolved / "dry_run.jsonl").is_file()
    assert (resolved / "frames" / "00000-tick0002.png").is_file()


def test_resolve_run_by_bare_name_prefers_directory(tmp_path):
    runs_root = tmp_path / "runs"
    run_dir = make_run(runs_root)

    assert resolve_run(run_dir.name, runs_root) == run_dir


def test_resolve_run_by_bare_name_falls_back_to_archive(tmp_path):
    runs_root = tmp_path / "runs"
    run_dir = make_run(runs_root)
    archive(run_dir, runs_root)
    for child in sorted(run_dir.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    run_dir.rmdir()

    resolved = resolve_run(run_dir.name, runs_root)

    assert resolved.name == run_dir.name
    assert (resolved / "dry_run.jsonl").is_file()


def test_resolve_run_defaults_to_latest_uncompressed(tmp_path):
    runs_root = tmp_path / "runs"
    make_run(runs_root, name="20260801-090000")
    newest = make_run(runs_root, name="20260801-212645")
    archive(newest, runs_root)

    assert resolve_run(None, runs_root) == newest


def test_resolve_run_lists_archives_when_none_uncompressed(tmp_path):
    runs_root = tmp_path / "runs"
    run_dir = make_run(runs_root)
    archive(run_dir, runs_root)
    for child in sorted(run_dir.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    run_dir.rmdir()

    with pytest.raises(SystemExit) as stop:
        resolve_run(None, runs_root)

    assert "20260801-212645" in str(stop.value)


def test_resolve_run_rejects_unknown_name(tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    with pytest.raises(SystemExit):
        resolve_run("nope", runs_root)


def test_find_journal_picks_the_only_jsonl(tmp_path):
    run_dir = make_run(tmp_path / "runs", journal="stage.jsonl")

    assert find_journal(run_dir, None) == run_dir / "stage.jsonl"


def test_find_journal_errors_without_any(tmp_path):
    run_dir = tmp_path / "runs" / "empty"
    run_dir.mkdir(parents=True)

    with pytest.raises(SystemExit):
        find_journal(run_dir, None)


def test_find_journal_errors_and_lists_when_ambiguous(tmp_path):
    run_dir = make_run(tmp_path / "runs")
    (run_dir / "strategy.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as stop:
        find_journal(run_dir, None)

    message = str(stop.value)
    assert "dry_run.jsonl" in message
    assert "strategy.jsonl" in message


def test_find_journal_honours_override(tmp_path):
    run_dir = make_run(tmp_path / "runs")
    (run_dir / "strategy.jsonl").write_text("", encoding="utf-8")

    assert find_journal(run_dir, "strategy.jsonl") == run_dir / "strategy.jsonl"


def test_find_journal_override_must_exist(tmp_path):
    run_dir = make_run(tmp_path / "runs")

    with pytest.raises(SystemExit):
        find_journal(run_dir, "missing.jsonl")


def test_load_entries_reads_every_line(tmp_path):
    run_dir = make_run(tmp_path / "runs")

    entries = load_entries(run_dir / "dry_run.jsonl")

    assert [entry["seq"] for entry in entries] == [0, 1, 2]
    assert entries[2]["trail"] == ["stage_list:ok"]


def test_load_entries_skips_blank_lines(tmp_path):
    run_dir = make_run(tmp_path / "runs")
    path = run_dir / "dry_run.jsonl"
    path.write_text("\n" + path.read_text(encoding="utf-8") + "\n   \n\n", encoding="utf-8")

    assert len(load_entries(path)) == 3


def test_load_entries_survives_a_truncated_line(tmp_path, capsys):
    run_dir = make_run(tmp_path / "runs")
    path = run_dir / "dry_run.jsonl"
    body = path.read_text(encoding="utf-8")
    path.write_text(body + '{"seq": 3, "t": 9.1, "kin', encoding="utf-8")

    entries = load_entries(path)

    assert [entry["seq"] for entry in entries] == [0, 1, 2]
    assert "跳過" in capsys.readouterr().err


def test_safe_frame_path_resolves_inside_run(tmp_path):
    run_dir = make_run(tmp_path / "runs")

    resolved = safe_frame_path(run_dir, "/frames/00000-tick0002.png")

    assert resolved == (run_dir / "frames" / "00000-tick0002.png").resolve()


def test_safe_frame_path_rejects_traversal(tmp_path):
    run_dir = make_run(tmp_path / "runs")
    (tmp_path / "secret.png").write_bytes(b"nope")

    assert safe_frame_path(run_dir, "/frames/../../secret.png") is None
    assert safe_frame_path(run_dir, "/frames/%2e%2e/%2e%2e/secret.png") is None


def test_safe_frame_path_returns_none_for_missing_file(tmp_path):
    run_dir = make_run(tmp_path / "runs")

    assert safe_frame_path(run_dir, "/frames/99999-tick9999.png") is None
