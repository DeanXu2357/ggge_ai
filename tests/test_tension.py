import logging

import pytest

from ggge_ai.sim import tension


def test_mp_max_is_twelve():
    assert tension.MP_MAX == 12


@pytest.mark.parametrize(
    "mp, expected_stage",
    [
        (0, 0),
        (3, 0),
        (4, 1),
        (7, 1),
        (8, 2),
        (11, 2),
        (12, 3),
    ],
)
def test_stage_boundaries(mp, expected_stage):
    assert tension.stage(mp) == expected_stage


@pytest.mark.parametrize("mp", [-1, 13])
def test_stage_rejects_out_of_range_mp(mp):
    with pytest.raises(ValueError):
        tension.stage(mp)


@pytest.mark.parametrize(
    "mp, expected_bonus",
    [
        (0, 0.0),
        (3, 0.0),
        (4, 0.10),
        (7, 0.10),
        (8, 0.20),
        (11, 0.20),
        (12, 0.30),
    ],
)
def test_damage_bonus_matches_stage(mp, expected_bonus):
    assert tension.damage_bonus(mp) == pytest.approx(expected_bonus)


def test_warn_not_modeled_logs_once(caplog):
    tension.warn_not_modeled.cache_clear()
    with caplog.at_level(logging.WARNING, logger="ggge_ai.sim.tension"):
        tension.warn_not_modeled()
        tension.warn_not_modeled()
        tension.warn_not_modeled()
    warnings = [r for r in caplog.records if "tension/MP not yet modeled" in r.message]
    assert len(warnings) == 1
