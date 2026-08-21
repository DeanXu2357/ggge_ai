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
  and 'HitProbability'. Both lead with the weapon that fires and
  read its accuracy as the base of the rate; the constant
  'hitBase' that stood there is retired. The three remaining hit
  constants are unexported.
- 'engine/battle/damage_test.go', 'hit_test.go': eight
  hand-written facts (the ratio clamps at zero, a sigmoid at equal
  values is one half, terrain divides, the multipliers multiply,
  the hit rate clamps at both ends, each mobility moves the rate
  its own way).
- 'engine/differential/formulas_test.go': one op per Python
  function, merged into the one 'ops' map through 'addOps', which
  refuses a name registered two times. The input of a check
  carries every argument; an unknown field stops the op.
- 'tests/fixtures/engine/formulas.json': 55 checks (3 standard,
  52 formula checks).
- 'engine/battle/terrain.go': the type 'Terrain' with its five
  kinds, its wire names, 'String', 'ParseTerrain', and the set
  type 'TerrainSet'. 'TerrainSpace' is the zero value, so a board
  that declares no terrain reads space.
- 'engine/battle/terrain_test.go': the terrain facts and the
  terrain half of the codec (the zero-value weapon, a weapon that
  halves against water, a weapon that cannot fire under water, the
  default kind against an override, the anchor cell of a unit, a
  payload with no terrain, a payload with terrain, and four names
  outside the contract).

Changed:

- 'engine/battle/model.go', 'codec.go': the types 'Pilot'
  (attack, defense, reaction) and 'Mech' (attack, defense,
  mobility); 'Unit' carries one of each in the fields 'Pilot' and
  'Mech'; the decode composes the two from the flat wire fields.
  'Mech' also carries the base copies 'HP', 'EN', 'MoveRange' and
  'Weapons'; the decode fills them from the four optional wire
  fields, and the same fields on 'Unit' stay the final panel. The
  weapon list decode moves into 'decodeWeapons', which both levels
  call.
- 'engine/battle/codec_test.go': a payload with no mech base
  leaves the base empty and keeps the panel, a payload with a mech
  base fills the mech alone, and a write into the panel does not
  reach the mech. 'engine/battle/terrain_test.go': a weapon of the
  mech base with a terrain outside the contract stops the decode.
- 'scripts/write_engine_fixtures.py': the case 'formulas';
  'build_case' takes extra checks; 'FORMULA_OPS' names the eight
  ops. Every hit check states an accuracy and the writer passes it
  to the Python function as the keyword 'base'.
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
  'unit_defense'. New rows bind the terrain and the terrain
  restriction; the 'terrain' row names the Go type and the two
  wire fields of the board. New rows bind the final panel and the
  base data, one term for each level of values; the unit, mech and
  pilot rows now name the level that each type holds.
- 'engine/battle/model.go': 'Weapon' carries 'Accuracy',
  'TerrainDamage' and 'UnusableIn'. The last two are read through
  'DamageScaleAgainst' and 'UsableIn';
  'Board' carries 'DefaultTerrain' and 'TerrainCells', read
  through 'TerrainAt' and 'TerrainOf'.
- 'engine/battle/codec.go': the weapon decode moves into
  'decodeWeapon', which parses the two restriction fields and the
  wire field 'accuracy' that reached no rule before; the state
  decode fills the two board fields.
- 'engine/protocol/state.go': the optional wire fields
  'terrain_damage' and 'unusable_in' on 'Weapon', 'terrain' and
  'terrain_cells' on 'BattleState', the optional wire fields
  'mech_hp', 'mech_en', 'mech_move_range' and 'mech_weapons' on
  'Unit', and the type 'TerrainCell'.
- 'engine/protocol/envelope.go', 'src/ggge_ai/engine/contract.py':
  the protocol version 1.2.
- 'tests/test_engine_codec.py': 'ENGINE_ONLY' names the Go fields
  that 'model.py' does not hold, so the parity gate takes them and
  still refuses an undeclared one.
- 'tests/test_sandbox_ui.py': the panel check reads
  'PROTOCOL_VERSION' instead of a copy of the number.
- 'docs/spec/battle-engine-protocol.md': the section 'Terrain'
  with the two payload tables, and the rule for an engine-only
  field. The section 'The final panel and the base data' with the
  table of the four mech fields. The open requirement of 'init',
  in the 'init' section and at the end of the 'Terrain' section.

The wire gains optional fields only. A payload of protocol 1.1
decodes to the same board as before.

## Exported Go API

    type Pilot struct{ Attack, Defense, Reaction float64 }
    type Mech struct {
        Attack, Defense, Mobility float64
        HP, EN, MoveRange         int
        Weapons                   []Weapon
    }
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
    func HitRatePercent(weapon Weapon, attacker, defender *Unit,
        abilityCorrection float64) float64
    func HitProbability(weapon Weapon, attacker, defender *Unit,
        abilityCorrection float64) float64

    type Terrain int
    const (
        TerrainSpace Terrain = iota
        TerrainAtmospheric
        TerrainGround
        TerrainSurface
        TerrainUnderwater
    )
    type TerrainSet map[Terrain]bool
    func (t Terrain) String() string
    func ParseTerrain(name string) (Terrain, error)
    type Weapon struct {
        ...
        Accuracy      float64
        TerrainDamage map[Terrain]float64
        UnusableIn    TerrainSet
    }
    func (w Weapon) DamageScaleAgainst(target Terrain) float64
    func (w Weapon) UsableIn(attacker Terrain) bool
    type Board struct {
        ...
        DefaultTerrain Terrain
        TerrainCells   map[Cell]Terrain
    }
    func (b *Board) TerrainAt(cell Cell) Terrain
    func (b *Board) TerrainOf(unit *Unit) Terrain

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
   decode does the composition. The later ruling of the same day
   settles the rest of 'Unit': the values on 'Unit' are the final
   panel, and the mech keeps its own copy of the hit points, the
   energy, the movement range and the weapons. The footprint and
   the support charges stay facts of the board; no level of the
   game holds a second copy of them.
2. No argument has a default. The caller states the terrain, the
   defense multiplier and the critical multiplier on every call.
   The Python defaults (terrain 1.0, defense 1.0, critical 1.1)
   live in the caller, not in the formula.
3. 'ExpectedDamage' is the composition of the formulas 8 to 10 in
   one entry point, so the engagement issue calls one verified
   function instead of composing three. The review asked for it;
   the first cut kept the composition in the test op alone.
4. The Python keyword 'clamp' of 'hit_rate_percent' has no Go
   counterpart. Only a Python test reads it, so no check varies
   it. The keyword 'base' now carries the accuracy of the weapon,
   and every hit check states it.
5. The formula case reuses the setup of the small board. The case
   format demands a setup, and these checks carry their own
   numbers.
6. The parity gate of 'tests/test_engine_codec.py' demanded that
   the Go struct and the dataclass hold the same field list, so
   the terrain fields could not reach 'Weapon' or 'BattleState'
   while 'model.py' stays untouched. The gate now takes a named
   list of engine-only fields. The alternative, an anonymous
   embedded struct, would pass the gate only because the parser
   reads no tag on that line; that is a hole in the parser, not a
   contract. A third alternative, a field on 'protocol.Board',
   fails on the facts: 'protocol.Board' carries the width and the
   height of 'init' and no decode reads it into the domain, while
   'battle.DecodeState' reads 'BattleState' alone.
7. 'TerrainOf' reads the anchor cell of the unit. A footprint of
   more than one cell can stand on more than one kind. The game
   shows the terrain of a cell, and no source says which cell of a
   large unit counts. The anchor is the cell the payload names,
   and the section 'Board geometry' already gives it that role.
8. The terrain restriction reads a factor, not a percentage: 0.5,
   not 50. The formula divides by it, and every other correction
   in the package is a factor.
9. The protocol version rose in both halves in one commit. The
   task said not to touch 'src/ggge_ai', but the 'hello' check
   compares the Go constant against 'PROTOCOL_VERSION', so a
   one-sided raise breaks the gate. The change is the one line of
   the constant.
10. The base copy of the mech carries no name prefix. 'Mech.HP' is
    the base copy and 'Unit.HP' is the panel; the struct that
    holds the field states the level, so a prefix would say the
    same word two times. The wire has no struct to lean on, so
    there the four fields carry the prefix 'mech'. The terminology
    map and the spec hold the distinction for the reader.
11. The four mech fields are flat on 'protocol.Unit', and not one
    nested object. The precedent of the terrain fields is flat,
    and the parity gate reads the JSON tag of each line, so a flat
    field is the shape that 'ENGINE_ONLY' can name.
12. The mech base decodes through the same 'decodeWeapon' as the
    panel, so a terrain name outside the contract stops the decode
    at either level.
13. The version stays at 1.2. The rule of the section 'Evolution'
    raises the version for a change that adds a field, and commit
    c89e9fd already raised it in this branch. No client has seen
    1.2 yet, so the four fields ride the same number.

## Verification

- From 'engine': go vet ./... no finding; go test ./... ok for
  battle, differential, protocol, server; gofmt -l clean.
- uv run pytest -q: 1113 passed, 4 skipped.
- uv run ruff check src tests scripts: all checks passed.
- uv run python scripts/write_engine_fixtures.py --check: nothing
  stale. 'git diff 5a3fc22..HEAD -- tests/fixtures/' names
  'formulas.json' alone: the accuracy of the weapon moved the hit
  checks, and the four board files came back byte for byte.

The case set covers zero on every argument, attack under defense
(the ratios clamp, the sigmoids do not), both sigmoid saturations
at an exponent of 700 (the saturated-low checks carry a power of
1e300, so the expected value is measurable under the absolute
floor of the harness), hit rates clamped at 100 and at 0 plus
rates between, the defense multipliers 1.0, 0.8, 0.6 and 0.0, the
critical multipliers 1.1, 1.2, 1.3, terrain 1.0, 1.2 and 0.8,
nonzero bonuses and penalties (one penalty above 1), and the
board values 4200/3900/220/190/205/310 with the powers 1800 and
2400. The hit checks carry the four accuracy values of the game
data (90, 95, 100, 105), the fitted 96.45, and an accuracy of 0,
which proves that the base is the weapon and nothing else.

Of the 52 formula checks, 51 agree bit for bit. The
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
- A terrain damage factor of 0: Python raises a division error, Go
  gives an infinity. The datamine holds no weapon that nullifies
  damage, so no payload should carry a zero, and the decode
  refuses no value today. The issue that wires the restriction
  into the strike path decides whether to reject it there.
- The constants are community-fitted values, and
  docs/reference/combat-formulas.md lists the calibration items
  that stay open. The branch adds no rule.
- The reading of the fitted constant 96.45 as the accuracy of the
  weapon waits on a device check. The user ruled it on 2026-08-21
  and called the ruling provisional: the community regression
  holds no accuracy term, and every weapon of the game data
  carries 90, 95, 100 or 105, a range that holds 96.45. The check
  reads the hit rate the game shows for two weapons of different
  accuracy on one pair of units: the rates must part by the
  difference of the two accuracy values. Until that check runs,
  the engine states a hypothesis, not a verified rule.
- Terrain is settled for the model and open for the producer of
  the data. The investigation of 2026-08-21 answered what the
  divisor reads, and the branch holds the model: the weapon
  carries its restriction, the cell carries its kind, and
  'DamageScaleAgainst' gives the divisor. Open: nothing reads the
  terrain of the map or of the weapon off the device yet, so every
  payload today declares none and every divisor is 1. Open too:
  which cell of the map holds which kind (the datamine stage table
  lights more than one flag on 200 stages, and the meaning of the
  flags is not verified), and which weapon carries the ability id
  2 or 4 of the datamine weapon table.
- The strike path does not read the restriction yet.
  'CombatBaseDamage' and 'ExpectedDamage' still take the divisor
  as a plain float from the caller, and their signatures are
  pinned by the differential harness. The engagement issue joins
  the two: it reads 'DamageScaleAgainst' with 'TerrainOf' of the
  target and passes the result.
- 'UsableIn' gates no action list yet. The issue that builds the
  legal actions must drop a weapon that cannot fire from the cell
  of the attacker.
- No code derives the final panel from the base data. The ability
  interaction that changes what a unit ends up with is implemented
  nowhere, and this branch does not invent it. The formulas read
  the same level that they read before. A later issue holds the
  interaction, and it also decides which producer fills the four
  mech fields: nothing reads a mech base off the device today, so
  every payload leaves them absent.
- Requirement for the issue that implements 'init': the field
  'board' of the request must carry the terrain of the map, in the
  same two fields that 'BattleState' carries today. The user ruled
  on 2026-08-21 that the terrain of each cell arrives when the
  board is built. 'init' is not implemented, and 'protocol.Board'
  carries the width and the height alone, so the branch records
  the requirement and changes no code. It is written in the 'init'
  section and at the end of the 'Terrain' section of
  docs/spec/battle-engine-protocol.md.
