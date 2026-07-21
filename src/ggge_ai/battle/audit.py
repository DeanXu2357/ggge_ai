"""Turn-level HP audit (silent-events batch B, issue #27).

Split from reconcile.py by design: reconcile attributes one of OUR attacks
across the sim/forecast/outcome layers; audit works at turn granularity and
covers the events we never saw stop to interact -- an enemy MAP weapon, an
off-screen enemy-vs-third-party engagement, an enemy self-buff/supply. It
rides the numeric read points that already exist (the tracker `_set_hp`
sink): whenever the screen hands back an HP value, the prior belief is
compared against it. A residual outside tolerance is NOT explained here --
live records it raw (ledger `unattributed_damage`) as offline-attribution
material for the closure layer (batch C); the screen stays authoritative and
the caller overwrites the belief regardless.

Scope: only screen-read HP flows through `_set_hp`, so only it triggers the
audit. The subtraction estimate (on_outcome certain-hit path) and
definition-file seeding write `belief.hp` WITHOUT `_set_hp` and are left
un-audited on purpose -- neither is a fresh reading, so a residual there
would be a self-comparison, not a silent event. EN is not audited this batch
(no freshness column; batch A deferred it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import Point
    from .tracker import UnitBelief

# v1 records every non-zero residual: live does no interpretation, so the
# thresholds (OCR noise vs a real event) are the batch-C open question,
# calibrated from field data. Constantized so a later batch tunes one place.
AUDIT_TOL_ABS = 0
AUDIT_TOL_RATIO = 0.0


@dataclass(frozen=True)
class HpDivergence:
    uid: str
    expected_hp: int
    observed_hp: int
    delta: int
    turn: int
    read_source: str
    prior_source: str
    prior_hp_turn: int
    world_pos: Point | None


def check_hp_divergence(
    belief: UnitBelief,
    observed_hp: int,
    turn: int,
    source: str,
    *,
    tol_abs: int,
    tol_ratio: float,
) -> HpDivergence | None:
    """Compare a screen-read HP against the carried belief. Returns a
    HpDivergence when the residual exceeds max(tol_abs, tol_ratio * prior),
    else None. A None prior (first read of a unit) has nothing to reconcile
    against. Both signs are reported: a negative delta is unattributed
    damage, a positive delta unattributed recovery."""
    prior = belief.hp
    if prior is None:
        return None
    delta = observed_hp - prior
    if abs(delta) <= max(tol_abs, tol_ratio * prior):
        return None
    return HpDivergence(
        uid=belief.uid,
        expected_hp=prior,
        observed_hp=observed_hp,
        delta=delta,
        turn=turn,
        read_source=source,
        prior_source=belief.source,
        prior_hp_turn=belief.hp_turn,
        world_pos=belief.world_pos,
    )
