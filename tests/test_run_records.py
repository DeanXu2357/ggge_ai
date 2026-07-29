"""執行紀錄完備化：逐 tick 原生幀入 run 目錄、舊 run 壓縮輪替。"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import cv2
import numpy as np

from ggge_ai.cli import rotate_default_runs
from ggge_ai.contracts import Ending, HiddenPolicy, Objective, StageOrder
from ggge_ai.runtime.journal import ARCHIVE_SUFFIX, FRAMES_DIRNAME, FrameStore, rotate_runs
from ggge_ai.runtime.perceive import Observation
from ggge_ai.stage.goals import Annihilation
from ggge_ai.stage.run import JOURNAL_NAME, run_stage, stage_journal
from tests.fixtures.stage_offline import (
    FakeExecutor,
    MockAdvisor,
    ScriptedPerceiver,
    battle,
    kills_everything,
)


def stage(tmp_path, frames):
    return run_stage(
        StageOrder(
            stage="S01",
            objectives=frozenset({Objective.CLEAR}),
            hidden_policy=HiddenPolicy.DECLINE,
            max_ticks=10,
        ),
        perceiver=ScriptedPerceiver(list(frames)),
        executor=FakeExecutor(),
        advisor=MockAdvisor(kills_everything()),
        victory=Annihilation(),
        journal=stage_journal(tmp_path),
    )


def ticks_of(tmp_path):
    text = (tmp_path / JOURNAL_NAME).read_text(encoding="utf-8")
    lines = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [line for line in lines if line["kind"] == "tick"]


def script(*shots: bytes | None):
    fighting = battle(allies=["a1"], enemies=["e1"])
    cleared = battle(allies=["a1"], enemies=[], actionable=[])
    return [
        Observation(screen="battle_map", state=fighting, frame=shots[0]),
        Observation(screen="battle_map", state=cleared, frame=shots[1]),
        Observation(screen="battle_result", terminal=Ending.VICTORY, frame=shots[2]),
    ]


def run_dirs(root: Path):
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir())


def make_run(root: Path, name: str, payload: str = "old") -> Path:
    run_dir = root / name
    (run_dir / FRAMES_DIRNAME).mkdir(parents=True)
    (run_dir / JOURNAL_NAME).write_text(payload + "\n", encoding="utf-8")
    (run_dir / FRAMES_DIRNAME / "00000-tick0001.png").write_bytes(payload.encode())
    return run_dir


def test_every_tick_stores_its_frame_and_the_journal_points_back_at_the_file(tmp_path):
    shots = (b"native-1", b"native-2", b"native-3")

    report = stage(tmp_path, script(*shots))
    ticks = ticks_of(tmp_path)

    assert report.ending is Ending.VICTORY
    assert len(ticks) == 3
    assert [(tmp_path / line["frame"]).read_bytes() for line in ticks] == list(shots)
    assert all(line["frame"].startswith(f"{FRAMES_DIRNAME}/") for line in ticks)


def test_the_frame_name_carries_the_tick_number_and_sorts_chronologically(tmp_path):
    stage(tmp_path, script(b"a", b"b", b"c"))
    ticks = ticks_of(tmp_path)

    names = [Path(line["frame"]).name for line in ticks]
    assert names == sorted(names)
    assert all(f"tick{line['tick']:04d}" in name for line, name in zip(ticks, names, strict=True))


def test_a_frameless_observation_changes_nothing_and_writes_no_frames_dir(tmp_path):
    report = stage(tmp_path, script(None, None, None))
    ticks = ticks_of(tmp_path)

    assert report.ending is Ending.VICTORY
    assert [line["outcome"] for line in ticks] == ["acted", "goal_met", "terminal"]
    assert all("frame" not in line for line in ticks)
    assert not (tmp_path / FRAMES_DIRNAME).exists()


def test_a_run_can_mix_ticks_with_and_without_a_frame(tmp_path):
    stage(tmp_path, script(b"only-the-first", None, None))
    ticks = ticks_of(tmp_path)

    assert (tmp_path / ticks[0]["frame"]).read_bytes() == b"only-the-first"
    assert [("frame" in line) for line in ticks] == [True, False, False]


def test_the_stored_png_keeps_the_native_resolution_it_arrived_with(tmp_path):
    image = np.zeros((1080, 2340, 3), dtype=np.uint8)
    image[100:200, 300:400] = 255
    encoded, buffer = cv2.imencode(".png", image)
    assert encoded
    payload = buffer.tobytes()

    name = FrameStore(tmp_path).save(payload, tick=1)

    assert (tmp_path / name).read_bytes() == payload
    assert cv2.imread(str(tmp_path / name), cv2.IMREAD_COLOR).shape == (1080, 2340, 3)


def test_the_same_tick_number_twice_never_overwrites_an_earlier_frame(tmp_path):
    store = FrameStore(tmp_path)

    first = store.save(b"first-stage", tick=1)
    second = store.save(b"second-stage", tick=1)

    assert first != second
    assert (tmp_path / first).read_bytes() == b"first-stage"
    assert (tmp_path / second).read_bytes() == b"second-stage"


def test_rotation_packs_every_old_run_dir_and_deletes_the_original(tmp_path):
    make_run(tmp_path, "20260101-000000")
    make_run(tmp_path, "20260102-000000")

    archives = rotate_runs(tmp_path)

    assert [path.name for path in archives] == [
        "20260101-000000" + ARCHIVE_SUFFIX,
        "20260102-000000" + ARCHIVE_SUFFIX,
    ]
    assert all(path.is_file() for path in archives)
    assert run_dirs(tmp_path) == []


def test_the_archive_unpacks_back_into_the_original_tree(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    make_run(root, "20260101-000000", payload="journal-line")

    (archive,) = rotate_runs(root)
    restored = tmp_path / "restored"
    with tarfile.open(archive) as bundle:
        bundle.extractall(restored, filter="data")

    run_dir = restored / "20260101-000000"
    assert run_dir.joinpath(JOURNAL_NAME).read_text(encoding="utf-8") == "journal-line\n"
    assert run_dir.joinpath(FRAMES_DIRNAME, "00000-tick0001.png").read_bytes() == b"journal-line"


def test_an_already_compressed_run_is_skipped_untouched(tmp_path):
    settled = tmp_path / ("20260101-000000" + ARCHIVE_SUFFIX)
    settled.write_bytes(b"already-packed")
    make_run(tmp_path, "20260102-000000")

    archives = rotate_runs(tmp_path)

    assert [path.name for path in archives] == ["20260102-000000" + ARCHIVE_SUFFIX]
    assert settled.read_bytes() == b"already-packed"


def test_only_the_newest_run_dir_is_left_uncompressed(tmp_path):
    make_run(tmp_path, "20260101-000000")
    make_run(tmp_path, "20260102-000000")

    rotate_runs(tmp_path)
    newest = make_run(tmp_path, "20260103-000000")

    assert run_dirs(tmp_path) == [newest.name]


def test_rotation_of_a_missing_or_empty_root_is_a_no_op(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    assert rotate_runs(tmp_path / "nowhere") == ()
    assert rotate_runs(empty) == ()
    assert not (tmp_path / "nowhere").exists()


def test_no_staging_leftovers_survive_a_rotation(tmp_path):
    make_run(tmp_path, "20260101-000000")

    rotate_runs(tmp_path)

    assert sorted(path.name for path in tmp_path.iterdir()) == ["20260101-000000" + ARCHIVE_SUFFIX]


def test_an_explicit_run_dir_leaves_the_runs_root_alone(tmp_path):
    make_run(tmp_path, "20260101-000000")

    archives = rotate_default_runs(str(tmp_path / "explicit"), runs_root=tmp_path)

    assert archives == ()
    assert run_dirs(tmp_path) == ["20260101-000000"]


def test_the_default_run_dir_rotates_the_root_before_the_run_starts(tmp_path):
    make_run(tmp_path, "20260101-000000")

    archives = rotate_default_runs(None, runs_root=tmp_path)

    assert [path.name for path in archives] == ["20260101-000000" + ARCHIVE_SUFFIX]
    assert run_dirs(tmp_path) == []
