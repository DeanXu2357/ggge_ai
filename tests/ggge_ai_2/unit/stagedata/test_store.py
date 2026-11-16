"""The stage store writes and reads one app version of a stage.

The suite needs a database. Set GGGE_DATABASE_URL to run it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import fields, is_dataclass

import numpy as np
import psycopg
import pytest

from ggge_ai_2.gamedata.store import database_url
from ggge_ai_2.stagedata.contract import (
    Faction,
    NameMask,
    PilotState,
    StageData,
    StageUnit,
    Terrain,
    UnitBrief,
    UnitDetail,
    UnitRole,
)
from ggge_ai_2.stagedata.store import PostgresStageStore

STAGE = "test-story-1-1-hard"

pytestmark = pytest.mark.skipif(
    "GGGE_DATABASE_URL" not in os.environ, reason="GGGE_DATABASE_URL is unset"
)


def mask(seed: int) -> NameMask:
    return NameMask(np.random.default_rng(seed).integers(0, 2, (14, 60), np.uint8) * 255)


def enemy(pos: tuple[int, int], seed: int) -> StageUnit:
    brief = UnitBrief(
        mech_role=UnitRole.ATTACK,
        mech_name=mask(seed),
        hp=5000 + seed,
        en=120,
        pilot_role=UnitRole.NO_ROLE,
        pilot_name=mask(seed + 100),
        mp=10,
        mp_max=40,
        state=PilotState.STRONG,
    )
    return StageUnit(pos, (1, 1), Faction.ENEMY, False, brief, UnitDetail())


def stage_data(app_version: str = "1.4.0", code_version: str = "9416000a") -> StageData:
    return StageData(
        stage=STAGE,
        app_version=app_version,
        code_version=code_version,
        columns=24,
        rows=14,
        terrain={(0, 0): frozenset({Terrain.SPACE}), (3, 2): frozenset(Terrain)},
        deploy_cells=((5, 7), (4, 7)),
        units=(enemy((10, 3), 1), enemy((12, 5), 2), enemy((0, 13), 3)),
        victory=(),
        events=(),
    )


def plain(value: object) -> object:
    if isinstance(value, NameMask):
        return (value.mask.dtype.str, value.mask.shape, value.mask.tobytes())
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(plain(item) for item in value)
    return value


@pytest.fixture
def store():
    with PostgresStageStore() as opened:
        yield opened
    with psycopg.connect(database_url(), autocommit=True) as connection:
        connection.execute("DELETE FROM stage WHERE id = %s", (STAGE,))


def test_a_saved_stage_loads_back_whole(store):
    data = stage_data()

    store.save(data)

    loaded = store.load(STAGE, "1.4.0")
    assert loaded is not None
    assert plain(loaded) == plain(data)


def test_a_stage_without_data_of_the_app_version_loads_none(store):
    store.save(stage_data("1.4.0"))

    assert store.load(STAGE, "1.5.0") is None


def test_two_app_versions_of_one_stage_live_side_by_side(store):
    store.save(stage_data("1.4.0", "aaaaaaaa"))
    store.save(stage_data("1.5.0", "bbbbbbbb"))

    old, new = store.load(STAGE, "1.4.0"), store.load(STAGE, "1.5.0")
    assert old is not None and new is not None
    assert (old.code_version, new.code_version) == ("aaaaaaaa", "bbbbbbbb")


def test_a_save_does_not_replace_the_data_of_the_same_app_version(store):
    store.save(stage_data("1.4.0", "aaaaaaaa"))

    with pytest.raises(psycopg.errors.UniqueViolation):
        store.save(stage_data("1.4.0", "bbbbbbbb"))
    loaded = store.load(STAGE, "1.4.0")
    assert loaded is not None
    assert loaded.code_version == "aaaaaaaa"
