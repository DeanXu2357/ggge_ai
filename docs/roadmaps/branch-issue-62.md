# Branch roadmap: issue 62, the damage and hit formulas

> Type: working—deleted at merge

## Resume point

The branch starts again from the new 'dev' (2d4006b, after the
geometry merge). The first attempt (branch 'issue-62-formulas-old',
tip ad49732) mirrored the Python keyword arguments with pointer
option structs. The user rejected that shape on 2026-08-21: the
engine follows Go conventions, it does not copy the Python
structure. This branch keeps none of that Go code.

## Plan

The formulas are game rules (docs/reference/combat-formulas.md).
They live in the domain package 'engine/battle' with the other
rules, as plain functions with explicit arguments.

1. 'engine/battle/model.go': 'Unit' gains the six values that the
   formulas read: 'UnitAttack', 'UnitDefense', 'PilotAttack',
   'PilotDefense', 'Reaction', 'Mobility'. 'codec.go' decodes
   them.
2. 'engine/battle/damage.go': the defense multipliers and the
   critical multipliers as constants; the six corrections as
   unexported functions; 'BaseDamage' (formula 5),
   'CombatBaseDamage' (formula 8), 'DamageScale' (formula 9),
   'FinalDamage' (formula 10), 'CriticalDamage' (formula 11). The
   two sides are '*Unit' values. Every multiplier is an argument;
   no argument has a default.
3. 'engine/battle/hit.go': 'HitRatePercent' and 'HitProbability',
   over '*Unit' and one ability correction. The rate is clamped to
   0 to 100. The Python keywords 'base' and 'clamp' have no Go
   counterpart: no consumer outside a Python test reads them.
4. 'engine/differential/formulas_test.go': one op for each of the
   eight Python functions. The input of a check carries every
   argument; the op decodes it with 'DisallowUnknownFields' and
   builds the two units. The op 'expected_damage' composes the
   three Go calls, because Go has no wrapper for that composition.
5. 'scripts/write_engine_fixtures.py' writes the case 'formulas'
   (tests/fixtures/engine/formulas.json). The case set covers: zero
   on every argument, attack under defense (the ratios clamp, the
   sigmoids do not), inputs that saturate a sigmoid, hit rates over
   100 and under 0, the multipliers of the reference document, and
   the board values the other cases use.
6. 'tests/test_engine_codec.py' accepts the new op names and
   asserts that the formula case holds every ported function.
7. Hand-written Go tests in 'engine/battle' for the facts a
   differential does not state: the ratio clamps at zero, a sigmoid
   at equal values is one half, the hit rate clamps at both ends.

Gates: uv run pytest -q; uv run ruff check src tests scripts; and
from 'engine': go vet ./... and go test ./...

## Progress log

- 2026-08-21: branch re-created from dev 2d4006b; plan written.
