# Branch roadmap: issue 62, the damage and hit formulas

> Type: working—deleted at merge

## Why the branch starts again

The first attempt (branch 'issue-62-formulas-old', tip ad49732)
stood on the old dev, before the engine got its own domain model,
and it mirrored the Python keyword arguments with pointer option
structs ('CombatBaseOptions{Terrain *float64}', 'value', 'Ptr').
The user rejected that shape on 2026-08-21: the engine follows Go
conventions and does not copy the Python structure. This branch
keeps none of that Go code. The old branch stays until the user
deletes it.

The same day the user ruled twice more on the model:
'engine/battle' does not mirror 'src/ggge_ai/sandbox/model.py' —
the Go domain model answers to the game, and any likeness to the
Python shape is coincidence, not a requirement. And the six combat
values do not sit flat on 'Unit': in the game a unit is a pilot
that rides a mech, and each level carries its own values.

## Change summary

The engine holds the damage formulas and the hit formulas of
docs/reference/combat-formulas.md as plain functions in the domain
package 'engine/battle'. Python is the oracle for the numbers only.

New:

- 'engine/battle/damage.go': the defense multipliers and the
  critical multipliers as constants; the six corrections
  (formulas 1 to 4, 6 and 7) as unexported functions that take
  'Pilot' and 'Mech' values, not loose floats, so the compiler
  rejects an argument swap; 'BaseDamage' (5),
  'CombatBaseDamage' (8), 'DamageScale' (9), 'FinalDamage' (10),
  'CriticalDamage' (11). Formula 2 and formula 4 read the mech,
  so their helpers are 'mechRatio' and 'mechSigmoid'.
- 'engine/battle/hit.go': 'HitRatePercent' (clamped to 0 to 100)
  and 'HitProbability'. The hit constants are unexported.
- 'engine/battle/damage_test.go', 'hit_test.go': eight
  hand-written facts (the ratio clamps at zero, a sigmoid at equal
  values is one half, terrain divides, the multipliers multiply,
  the hit rate clamps at both ends, each mobility moves the rate
  its own way).
- 'engine/differential/formulas_test.go': one op per Python
  function, merged into the one 'ops' map through 'addOps', which
  refuses a name registered two times. The input of a check
  carries every argument; an unknown field stops the op.
- 'tests/fixtures/engine/formulas.json': 54 checks (3 standard,
  51 formula checks).

Changed:

- 'engine/battle/model.go', 'codec.go': the types 'Pilot'
  (attack, defense, reaction) and 'Mech' (attack, defense,
  mobility); 'Unit' carries one of each in the fields 'Pilot' and
  'Mech'; the decode composes the two from the flat wire fields.
- 'scripts/write_engine_fixtures.py': the case 'formulas';
  'build_case' takes extra checks; 'FORMULA_OPS' names the eight
  ops.
- 'tests/test_engine_codec.py': freshness over every case the
  writer produces; the format test accepts the formula ops and
  still demands the three standard ops; a coverage test for the
  eight ops.
- 'docs/reference/terminology-map.md': bindings for the formula
  terms and the four correction terms; the 'ability correction'
  row names the dodge penalty as a sandbox placeholder; the
  'defense multiplier' row names the Go constants as defaults that
  the rules payload can override. New rows bind unit, mech and
  pilot, one term for each level; the rows that read "unit attack"
  and "unit defense" for a mech value now say mech, and the unit
  row records that the wire names stay 'unit_attack' and
  'unit_defense'.

Nothing changes on the wire: 'engine/protocol', the protocol
version and the spec are untouched.

## Exported Go API

    type Pilot struct{ Attack, Defense, Reaction float64 }
    type Mech struct{ Attack, Defense, Mobility float64 }
    type Unit struct {
        ...
        Pilot Pilot
        Mech  Mech
        ...
    }
    const NoDefenseMultiplier, DefendMultiplier, ShieldMultiplier
    const CritNormal, CritHighMorale, CritSuper
    func BaseDamage(power float64, attacker, defender *Unit) float64
    func CombatBaseDamage(power float64, attacker, defender *Unit,
        terrain float64) float64
    func DamageScale(bonuses, penalties float64) float64
    func FinalDamage(combatBase, scale, defense float64) float64
    func CriticalDamage(combatBase, scale, defense,
        critical float64) float64
    func ExpectedDamage(power float64, attacker, defender *Unit,
        terrain, bonuses, penalties, defense float64) float64
    func HitRatePercent(attacker, defender *Unit,
        abilityCorrection float64) float64
    func HitProbability(attacker, defender *Unit,
        abilityCorrection float64) float64

## Call chain

Python writes the inputs and its own outputs into
'formulas.json'. The Go test decodes one input for one op, builds
the two units, calls the formula, and the harness of #60 compares
the number against what Python wrote. Nothing in the server reads
the formulas yet: the engagement resolution (#64) is the first
caller.

## Contention points

1. The two sides of a strike are '*Unit' values, not six floats.
   The formulas read the values from the unit, and the engagement
   issue passes the units it already holds. The first cut put the
   six values flat on 'Unit', because the wire carries them flat
   and a flat copy is the shortest decode. The user ruling of
   2026-08-21 overrides that: the game holds two levels, so the
   model holds two levels. The flat wire keeps its names, and the
   decode does the composition. The rest of 'Unit' (HP, EN, move
   range, weapons, footprint, support charges) stays where it is;
   which of those belong to the mech and which to the pilot is a
   separate issue.
2. No argument has a default. The caller states the terrain, the
   defense multiplier and the critical multiplier on every call.
   The Python defaults (terrain 1.0, defense 1.0, critical 1.1)
   live in the caller, not in the formula.
3. 'ExpectedDamage' is the composition of the formulas 8 to 10 in
   one entry point, so the engagement issue calls one verified
   function instead of composing three. The review asked for it;
   the first cut kept the composition in the test op alone.
4. The Python keywords 'base' and 'clamp' of 'hit_rate_percent'
   have no Go counterpart. Only a Python test reads them, so no
   check varies them.
5. The formula case reuses the setup of the small board. The case
   format demands a setup, and these checks carry their own
   numbers.

## Verification

- From 'engine': go vet ./... no finding; go test ./... ok for
  battle, differential, protocol, server; gofmt -l clean.
- uv run pytest -q: 1113 passed, 4 skipped.
- uv run ruff check src tests scripts: all checks passed.
- uv run python scripts/write_engine_fixtures.py --check: nothing
  stale; the four earlier golden files came back byte for byte.

The case set covers zero on every argument, attack under defense
(the ratios clamp, the sigmoids do not), both sigmoid saturations
at an exponent of 700 (the saturated-low checks carry a power of
1e300, so the expected value is measurable under the absolute
floor of the harness), hit rates clamped at 100 and at 0 plus
rates between, the defense multipliers 1.0, 0.8, 0.6 and 0.0, the
critical multipliers 1.1, 1.2, 1.3, terrain 1.0, 1.2 and 0.8,
nonzero bonuses and penalties (one penalty above 1), and the
board values 4200/3900/220/190/205/310 with the powers 1800 and
2400.

Of the 51 formula checks, 50 agree bit for bit. The
saturated-low input of 'combat_base_damage' parts in the last
bit: the two runtimes call different libm code for 'exp'. The
harness tolerance takes it; no rule was loosened.

Code review (2026-08-21, high effort) found ten items; all but one
are applied in commits 5612522, cb1b058 and 9b16e30. Declined: the
removal of 'DefendMultiplier' and 'ShieldMultiplier'. They are the
reference defaults; the engagement issue reads the rules payload,
which can override them, and the terminology row says so.

## Open points

- A missing input field decodes as zero on the Go side; the
  writer always emits every field, so no case meets that hole.
- A terrain of 0: Python raises a division error, Go gives an
  infinity. Neither side has a guard today. The rules payload
  carries the terrain, and the issue that decodes the rules into
  the domain must reject a zero there.
- The constants are community-fitted values, and
  docs/reference/combat-formulas.md lists the calibration items
  that stay open. The branch adds no rule.
- Terrain stays open, and this branch does not own it. A separate
  investigation runs on terrain adaptability; its result decides
  what the divisor of formula 8 reads and where the value comes
  from. Until then 'CombatBaseDamage' and 'ExpectedDamage' take
  the terrain as a plain float from the caller.
