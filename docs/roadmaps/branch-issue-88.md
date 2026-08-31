# Branch roadmap: issue 88, the battle engine as definitions, state and systems

> Type: working—deleted at merge

Issue: #88. Branch: issue-88-engine-restructure. Status: awaiting-review.
Base: dev c65f416. The #72 branch (issue-72-mech-pilot-unit, head
9cad225) is the source of parts for #72 after this branch merges.

## Design (approved before code)

Note: 'engine/battle/def' and 'engine/battle/state' are back. The
commit 'ef77841' deleted them, and the commits 'c4a0edc', '0cc8dc5'
and 'd479bb2' wrote them again in a different shape. Contention
point 18 holds the two rulings, the difference between the attempts
and the cost. The two sections below record the shape that shipped.
Each one ends with the parts of the first design that died, and the
reason for each part.

Two data packages and two kinds of system package below the
contract 'engine/battle', and one shell. Imports run one way:
shell -> systems -> state -> def -> contract. The contract imports
no package of the engine, and 'formula' imports no package of the
engine. A system never imports another system except through the
pure ones (geometry, formula).

### Static definitions: 'engine/battle/def'

No rule writes a field of this package. A unit points at its mech
and at its pilot, so every copy of a battle shares them. The
package declares no vocabulary. It reads 'battle.Cell',
'battle.Direction', 'battle.WeaponCategory',
'battle.MapWeaponAffects', 'battle.SkillKind', 'battle.SkillSource'
and 'battle.SkillAffects' from the contract. The types carry no
JSON tag: the conversion is the only bridge to the wire.

    type Mech struct {
        HP, EN                      int
        Attack, Defense, Mobility   float64
        MoveRange                   int
        Weapons                     []Weapon
        MapWeapons                  []MapWeapon
    }
    type Pilot struct {
        Ranged, Melee, Awaken, Defense, Reaction float64
        SP                                      int
    }
    type Weapon struct {
        Name               string
        Power              float64
        RangeMin, RangeMax int
        ENCost             int
        Accuracy           float64
        UsableAfterMove    bool
        DebuffKind         *string
        DebuffMagnitude    float64
        Categories         []battle.WeaponCategory
    }
    type MapWeapon struct {
        Name                    string
        Power                   float64
        ApplyShape, EffectShape ShapeRange
        AmmoMax, ENCost         int
        Accuracy                float64
        Affects                 battle.MapWeaponAffects
        UsableAfterMove         bool
        DebuffKind              *string
        DebuffMagnitude         float64
        Categories              []battle.WeaponCategory
    }
    type ShapeRange struct {
        Cells     []battle.Cell
        Direction battle.Direction
    }
    type Skill struct {
        Kind            battle.SkillKind
        Source          battle.SkillSource
        Amount          *float64
        Uses            int
        EndsActivation  bool
        UsableAfterMove bool
        Affects         battle.SkillAffects
    }
    func (w Weapon) Reaches(distance int) bool
    func (w Weapon) Debuff() string

'Skill' is a type of 'def', but the skill list of a unit sits in
'state.UnitValue'. A use of a skill spends 'Uses', so the list is a
pool of the unit. The type is the shape of one entry only.

What the first design lost:

- 'RadiusRange' with 'Holds'. The weapon keeps the two integers of
  the wire, 'RangeMin' and 'RangeMax', and 'Weapon.Reaches' answers
  the distance question. A second shape for a pair of integers is
  one more mirror, and the mirror killed the first attempt.
- The flag 'MapWeapon'. The map weapon became its own type in
  'ca8ae83' (protocol 1.8), before this restructure.
- The declaration 'type WeaponCategory string' and its constants.
  The package reads the contract enum.
- The plain 'DebuffKind string'. The field keeps the '*string' of
  the wire. A plain string cannot tell an absent debuff from an
  empty one, and the round trip of contract_test.go compares the
  two forms field by field.

No 'CanCounter': a counter fires under the rule of an attack (user
ruling 2026-08-30). The ability fields of #72 land here later.

### Dynamic state: 'engine/battle/state'

The package holds what a battle writes. It declares three types and
re-declares nothing. 'battle.Cell', 'battle.Faction',
'battle.Bounds', 'battle.Terrain', 'battle.TerrainCell' and
'battle.Debuff' come from the contract.

    type Unit struct {
        ID        string
        Faction   battle.Faction
        Size      battle.Cell
        MaxHP, ENMax, SPMax                              int
        ChanceStepsMax                                   int
        SupportDefendChargesMax, SupportAttackChargesMax int
        HasShield, SupportDefendWhenAttack               bool
        Mech      *def.Mech
        Pilot     *def.Pilot
        Value     UnitValue
    }
    type UnitValue struct {
        Pos       battle.Cell
        HP, EN, SP                                 int
        Acted                                      bool
        ChanceSteps                                int
        SupportDefendCharges, SupportAttackCharges int
        Skills    []def.Skill
        Ammo      map[string]int
        Debuffs   []battle.Debuff
    }
    type Battle struct {
        Units        []Unit
        Phase        battle.Faction
        Turn         int
        Bounds       battle.Bounds
        Terrain      battle.Terrain
        TerrainCells []battle.TerrainCell
    }
    func (u *Unit) Alive() bool                  // nil receiver = dead
    func (u *Unit) Footprint() battle.Footprint
    func (b *Battle) Unit(id string) *Unit       // lookup, nil when absent
    func (b *Battle) PhaseIndex() int

The placement rule, which a reviewer applies to a new field:
'UnitValue' holds every field that a rule of a battle writes, plus
the three pools a unit spends ('SP', 'Ammo', 'Skills'). A maximum
is the bound of a pool and not a pool, so it stands for the whole
battle and sits on 'state.Unit'.

'state.Battle' holds no 'PendingEvents' and no 'FiredEvents'. The
two lists belong to the session of the handler
('engine/server/handler/session.go' fills them into the answer of
'export'), and 'Load' never took them.

The package holds no 'Clone'. 'battle.BattleState.Clone' is the one
deep copy of the engine, and the two conversion functions are its
callers.

What the first design lost:

- The vocabulary of the grid. The first 'state.go' declared 'Cell',
  'Size', 'Footprint', 'Bounds', 'Faction', 'Terrain', 'Debuff',
  'Skill' and the skill enums a second time. That is what killed it
  (contention point 18).
- 'Bounds{Low, High}'. The state holds 'battle.Bounds' by value.
  The contract holds a pointer to it, so the conversion reads
  through the pointer on the way in and takes an address on the way
  out.
- The 'Terrain' enum of int with the table 'Names'. 'battle.Terrain'
  is a string, and its value is its wire name.
- 'TerrainCells map[Cell]Terrain'. The state keeps the wire list, so
  an export answers in payload order.
- 'Footprint' as a field of a unit. The unit holds 'Size' and
  'Value.Pos' as the wire holds them, and 'Unit.Footprint' builds
  the rectangle. The state method does not lift a size of zero to
  one. 'board.validate' lifts it before the conversion runs.
- The name 'Board'. The type is 'state.Battle', and 'board.Board' is
  the shell.
- One flat unit. The unit splits in two: 'state.Unit' for the
  identity and the bounds, 'state.UnitValue' behind the named field
  'Value' for the eleven fields a battle writes.

### The conversion: 'engine/battle/state/contract.go'

    func FromContract(s battle.BattleState) Battle
    func (b *Battle) ToContract() battle.BattleState

It runs at two points and nowhere else: 'FromContract' in
'board.Load', 'ToContract' in 'board.State'. 'FromContract' clones
its input first and 'ToContract' clones its answer last, both
through 'battle.BattleState.Clone', so the answer of 'State' shares
nothing writable with the board. A mech and a pilot go into a local
before the conversion takes the address, so two units that carry
equal mechs never point at one mech.

### Pure systems (read, never write)

'engine/battle/geometry':

    func Distance(a, b battle.Footprint) int
    func FootprintAt(unit *state.Unit, anchor battle.Cell) battle.Footprint
    func AddFootprint(set CellSet, footprint battle.Footprint)
    func Occupied(board *state.Battle, except string) CellSet
    func Blocking(board *state.Battle, unit *state.Unit) CellSet
    func ReachableAnchors(board *state.Battle, unit *state.Unit) CellSet
    func SortedCells(set CellSet) []battle.Cell

The board argument is 'state.Battle' and the geometry types are the
contract types: 'Within' is 'battle.Footprint.Within'.

'engine/battle/abilities' arrives with #72 (condition sums, scaled
stats); in this issue the maxima come from the definitions alone.

### Writing systems

'engine/battle/engagement' — one activation of one unit: the move,
the exchange, the end of the activation.

    // The mirror types 'engagement.Decision' and 'engagement.Response'
    // are gone (contention point 14). The engagement speaks
    // 'battle.Decision' and 'battle.ResponseAttack'.

    // Prepare validates every participant and writes nothing. Every
    // error of 'Act' comes from here: battle.ErrNoUnit, ErrDestroyed,
    // ErrOffPhase, ErrActed, ErrIllegalMove, ErrIllegalAction.
    func Prepare(board *state.Battle, decision battle.Decision) (Plan, error)

    // Plan is the ordered list of steps with every choice resolved:
    // the anchor, the target, the weapon, each supporter with its
    // weapon and distance, the bearer, the stance, the counter weapon.
    type Plan struct { ... unexported ... }

    // Commit writes the plan in order and cannot fail. It stops when
    // the receiver of the next strike is destroyed; a shooter that
    // died earlier in the exchange is skipped.
    func Commit(board *state.Battle, plan Plan, dice battle.Dice) Trace

    // Menu answers 'response_attacks' with the same eligibility
    // helpers Prepare uses, so the menu and the check never diverge.
    // It returns 'Options' (contention point 5).
    func Menu(board *state.Battle, decision battle.Decision, defenderID string) (Options, error)

    type Trace []Strike; type Strike struct {Kind, ShooterID, StruckID,
    Weapon, Landed, Damage, Killed}; type Forecast; type Menu with the
    option types of today (results.go).

  Prepare, in order: the actor (exists, alive, of the phase, not
  acted); the kind (map_attack refused); the anchor (nil = stay;
  reachable; permitted after the move for the weapon); for an attack:
  the target (exists, alive, opposing), the weapon (exists, not a map
  weapon), the reach from the firing footprint, the EN; the bearer
  (named: same faction, alive, covers when attacking, a defend charge,
  within its move range of the firing footprint); the response
  (stance known; a counter weapon that is not a map weapon, reaches
  the firing footprint, the EN; a support defender: same faction,
  alive, a defend charge, within its move range of the defender, not
  with the defend stance; support attackers: at most three, unique,
  same faction, alive, an attack charge, within move range of the
  defender, a weapon that reaches the firing footprint with the EN;
  their 'other' for the EN is the attacker); the attacker's support
  attackers likewise against the target (their 'other' is the unit
  that takes the main strike).

  Commit, in order: the anchor; the actor's EN; the attacker's salvo
  (each supporter: charge, EN, one die for the salvo, strike); the
  main strike (the receiver is the defender's support defender when
  named — its charge — else the target with the stance multiplier;
  the hit rate reads the target); the exit point (user ruling
  2026-08-30): the exchange ends where the attacked unit would act
  but cannot because it is destroyed — the attacker's sequence runs
  whole (a main strike lands even on a target the salvo destroyed),
  and the defender's reply (its salvo, its counter) does not run when
  the defender is destroyed; a counter has no receiver when the
  attacker is destroyed by the defender's salvo (the goldens encode
  both); the defender's salvo; the counter (the bearer covers when it
  holds a charge — its charge; the EN of the counter is spent on a
  miss as well); the end of the activation (a kill with a chance step
  left spends the step and keeps the unit active, else acted).

'engine/battle/turn':

    func Advance(board *state.Battle) []Rotation    // phase rotation,
        // EN regeneration, debuff expiry, acted reset, as turn.go today

'engine/battle/deploy' is gone: the user folded it into the shell.
'assemble' is a function of board/resolver.go, and it runs on the
contract form before the conversion.

    func assemble(unit *battle.Unit)  // maxima from the definitions;
        // #72 adds the abilities. 'Place' comes with #72.

### The shell: 'engine/battle/board'

    type Board struct{ state state.Battle }  // implements battle.Board
    New()                                    // an empty board
    Load: assemble, validate, state.FromContract
    Act: engagement.Prepare -> engagement.Commit ->
         turn.Advance -> encode. Atomic by construction: Prepare
         returns before the first write and Commit cannot fail, so
         handler/act.go drops its clone.
    Actions, ReachableCells: geometry
    ResponseAttacks: engagement.Menu
    State: state.Battle.ToContract
    Summary, the read answers: codec.go

The conversion between the two forms is one file of the 'state'
package, not two files of the shell. The shell keeps 'codec.go' for
the answers of the read commands, which project the state onto the
wire answer types and hold no second form of a unit.

### Rule of writes

Only 'engagement/commit.go' and 'turn/turn.go' assign a field of
'state.Unit' or 'state.Battle' during a battle. Before the battle,
'board/resolver.go' ('assemble', 'validate') writes 'battle.Unit'
fields on the contract form, and 'state/contract.go' writes both
forms in the conversion. 'battle/helpers.go' ('Clone') writes the
copy. Review check: grep for assignments to those fields outside
the two systems, the shell and the conversion.

### Stages (each with every gate green and the goldens byte-identical)

A. 'def', 'state', 'geometry' introduced; the existing board code
   rewired to them mechanically (the flow untouched).
B. 'engagement' (Prepare/Commit/Menu), 'turn', 'deploy' written from
   the design; the old resolve.go, strike.go, forecast.go,
   response_attacks.go, results.go deleted; the shell reduced.
C. 'can_counter' removed (protocol 1.5, Python mirror, fixtures,
   scenario placeholder); handler clone dropped.
D. Spec process model, terminology map, ledger, the artifact.

## Progress log

- 2026-08-30: the design above, for the user's approval before code.
- 2026-08-30: approved ("開始吧"); the exit point of the exchange
  stated by the user. Stage A starts.
- 2026-08-30: stage A (c27751f, 077f5d1, 1e2fa3a), stage B
  (373a69d, 15d62c2), stage C (04dbde7, 6e943b2, 2d5e28f), stage D
  (02a8784, 178dec3). Every stage: gates green, goldens byte-identical
  apart from the removed key.
- 2026-08-30: '/code-review' (high): ten findings, eight code fixes
  in cdb3c4d..a08ca8e, two docs fixes in 9dcce91 and this commit.
- 2026-08-31: the weapon split into 'Weapon' and 'MapWeapon' with the
  new type 'ShapeRange' (protocol 1.8). Shape only; no firing.
- 2026-08-31: the user ruled the area fields of 'MapWeapon':
  'ApplyShape' and 'EffectShape', with no 'Origin' and no
  'CenterRange' (protocol 1.9, a429965).
- 2026-08-31: the user reversed 'ef77841'. 'def' and 'state' come
  back, and 'battle' stays the one vocabulary. Three commits:
  c4a0edc (the two packages, nothing imports them), 0cc8dc5 (the
  conversion, nothing calls it), d479bb2 (the systems and the shell
  on the state form). The wire did not move: no fixture, no
  scenario, no Python file and no protocol version changed.
- 2026-08-31: this commit records the reversal in the two design
  sections, in contention point 18, in the spec, in the terminology
  map and in the ledger.

## Change summary

| Commit | What |
|---|---|
| 2015ab0, c7dbd1a | The design and the ledger entries of the 0830 rulings |
| c27751f | 'engine/battle/def' and 'engine/battle/state'; the board decodes into them, the definitions included |
| 077f5d1 | 'engine/battle/geometry'; the board reads it |
| 1e2fa3a | The state clone test: definitions shared, state copied |
| 373a69d | 'engine/battle/engagement' ('Prepare', 'Commit', 'Menu', the decision and result types), 'engine/battle/turn' ('Advance', 'PhaseIndex', 'Pending', 'Gone'), 'engine/battle/deploy' ('Assemble'); the board still drove the old flow |
| 15d62c2 | The board reduced to the shell: 'Act' = 'Prepare', 'Commit', 'turn.Advance'; resolve.go, strike.go, forecast.go, response_attacks.go, results.go, turn.go, model.go deleted; tests moved |
| 04dbde7 | The handler runs 'Act' on the session board; a clone only on the forced-dice path; the atomicity test |
| 6e943b2 | 'can_counter' removed from the definitions, the codecs, the wire (protocol 1.5), the Python mirror, the fixtures (306 lines) and the scenario placeholder |
| 2d5e28f | The counter rule and the 1.5 entry in the spec; the datamine note |
| 02a8784, 178dec3 | The spec process model, the terminology rows, this artifact |
| cdb3c4d, 91654ed, c616c12, 226c6b5, 8238ddc, 70511fd, 73fa207, a08ca8e | The code-review fixes: one 'state.Unit.Alive' and one 'engagement.LivingUnit'/'OnPhase'; 'state.PhaseOrder'/'Board.PhaseIndex' (engagement no longer imports turn); 'ReachableCells' through 'LivingUnit'; one 'fires' predicate; 'receiverFor' replaces the plan's mirror of the receiver; 'Menu' through 'Prepare'; the Python hello version check; the tolerant intel load |
| cb3d66b | The board query 'Capabilities' renamed 'Actions' after the wire command; the private 'capabilities' struct removed (a user finding at review: the word named four things in one function and reads as a synonym of the issue 72 abilities) |
| 3a5e186 | 'Apply' removed: the golden 'apply' checks pass through 'Act' (a user finding at review) |
| 414ff43 | 'Plan.Draws' bounds the forced 'outcomes' list before the first write; the handler keeps no clone of the board or the generator; 'ServerDraw.Clone' and 'ManualRoll.Short' gone |
| 4a5d3da | The board files re-homed by role: 'Load'/'assemble'/'validate' in resolver.go, codec.go conversions only, tests sorted by subject, the value-helper tests moved to the battle package |
| 312bac1 | One 'Load' on 'BoardResolver' for init and load; the factory gone; 'main.go' injects 'board.New()'; assembly on both paths fills only zeros; the bounds check judges the load path; the enemies rule in the init handler (a user ruling) |
| 92ec720 | 'Clone' left 'BoardReader': no production caller since the dice bound; 'BattleState.Clone' stays (a user ruling) |
| 119ebd8 | 'battle.BoardFactory' on the contract; 'main.go' injects 'board.Factory'; the handler no longer imports the concrete board package (a user ruling) |
| c272c45 | The deploy package folded into the shell (a user ruling): 'NewBoard(bounds, terrain, terrainCells, enemies)' builds and assembles a new battle, 'Restore(state)' rebuilds a snapshot with no assembly, the handler parses and passes fields |
| 4722c31 | 'board.NewBoard' from a 'battle.BattleState' for init, load and the tests; 'deploy.Opening' assembles the opening state; the handler parses 'InitRequest'; 'load' no longer rotates (a user ruling); 'Board.Advance' gone; 'ErrOutsideContract' in 'battle' |
| f378713 | The four commands with no handler ('rollback', 'set_unit', 'advice', 'certify') and their types, the goal/budget/verdict types and the chance-event types left the contract and the Python mirror (a user ruling) |
| ef77841 | The state and definition packages deleted; the systems and the shell work on the contract types ('helpers.go' holds the value helpers); the codec keeps validation, init assembly and the response projections (762 to 350 lines); 'reachableCells' inlined; the test-only helpers 'terrainAt'/'terrainOf'/'unit' gone |
| b716a32 | The contract types moved from 'engine/protocol' to 'engine/battle' ('decision.go', 'snapshot.go', 'responses.go'); 'actions' refuses an acted unit, protocol 1.6 |
| 15de5e6, f317328 | The board files sorted by contract role ('reader.go', 'resolver.go', 'codec.go' with the definition codec merged, 'board.go' the state) after a user finding at review; the dead map 'wireKinds' dropped |
| 507fb40 | The mirror 'engagement.Decision', 'engagement.Response' and their enums removed: the engagement speaks 'battle.Decision', the board loses the decode layer, 'Act' and 'ResponseAttacks' pass the payload through (a user finding at review) |
| de450a9 | The composition of the 'actions' answer moved from the codec to reader.go as 'actionsOf': it selects what the actionable list of one unit holds, so it is the business logic of the query and no conversion; the test helper of the old name is 'mustActions' (a user finding at review) |
| 9dcce91, 2732e7e | The terminology drift of 178dec3 (the joined unit/mech row, two paths, the forecast row, the row 'salvo'), the spec import sentence, this artifact |
| ca8ae83, a429965 | The map weapon split out of 'battle.Weapon' as 'battle.MapWeapon' with 'ShapeRange' (protocol 1.8), then the two shapes 'ApplyShape' and 'EffectShape' (protocol 1.9), both user rulings; see contention points 16 and 17 |
| c4a0edc | 'engine/battle/def' and 'engine/battle/state'; the two packages declare no vocabulary of the contract, and nothing imports them yet; the field-partition test of state_test.go |
| 0cc8dc5 | 'state.FromContract' and 'state.Battle.ToContract'; the reflection round trip and the sharing test of contract_test.go; nothing calls the two functions yet |
| d479bb2 | The systems and the shell on the state form: 'engagement', 'turn', 'geometry' and 'board' take 'state.Battle' and 'state.Unit', and every write of a pool goes through 'Value'; 'Load' converts in and 'State' converts out; five value helpers leave helpers.go with their callers; 'assemble' and 'validate' keep their signatures on the contract form |
| this commit | The reversal in the two design sections, contention point 18, the spec process model, three terminology rows and the ledger entry of 2026-08-31 |

    engine/battle             board.go (the three interfaces),
                              decision.go, snapshot.go,
                              responses.go (the wire types),
                              helpers.go (140): Terrain,
                              WeaponCategory, 'Cell.Before',
                              Footprint and its methods,
                              'Unit.Footprint', PhaseOrder,
                              'Faction.Opposing', 'Clone',
                              'cloneUnit', 'CloneAmount';
                              dice.go, errors.go
    engine/battle/def         def.go (79): Mech, Pilot, Weapon,
                              MapWeapon, Skill, ShapeRange,
                              'Weapon.Reaches', 'Weapon.Debuff'
    engine/battle/state       state.go (82): Unit, UnitValue, Battle,
                              'Unit.Alive', 'Unit.Footprint',
                              'Battle.Unit', 'Battle.PhaseIndex';
                              contract.go (268): 'FromContract',
                              'ToContract' and the per-type
                              conversions; state_test.go (the field
                              partition), contract_test.go (the round
                              trip, the sharing, the two mechs)
    engine/battle/geometry    geometry.go (143)
    engine/battle/engagement  model.go (the shared predicates,
                              'nameOf'),
                              prepare.go (263), commit.go (210),
                              menu.go (107), strike.go (100),
                              support.go (54), forecast.go, results.go
    engine/battle/turn        turn.go (102)
    engine/battle/board       board.go (the struct and 'New'),
                              reader.go ('BoardReader'),
                              resolver.go ('BoardResolver': 'Load',
                              'assemble', 'validate', 'Act'),
                              codec.go (the read answers); tests by
                              subject: resolver_test.go,
                              reader_test.go, codec_test.go,
                              geometry_test.go, turn_test.go (the
                              value-helper tests live in
                              engine/battle/helpers_test.go)
    engine/server/handler     act.go
    engine/protocol           types.go (the per-command wrappers),
                              envelope.go (1.9), commands.go,
                              state.go
    src/ggge_ai/engine        state.py, codec.py, contract.py (1.9)

## Call chain

    act {unit_id, action, response_attack, dice}
      handler.Commands.Act
        target = session board (a clone only when the dice are forced)
        board.Act(decision, dice)                       the shell
          engagement.Prepare(b.state, decision)         reads only
            actor: exists, alive, of the phase, not acted
            kind: attack | reposition | standby (map_attack refused)
            anchor: reachable (geometry), permitted after the move
            attack: target (alive, opposing), weapon (not map, exists),
              EN, reach (geometry.Distance), the actor's supporters
              (<= 3, unique, eligible), the bearer, the response
              (stance, counter weapon, support defender, the
              defender's supporters)
            -> Plan, or the first error
          engagement.Commit(b.state, plan, dice)       writes, cannot fail
            anchor; actor.Value.EN -= cost
            salvo of the actor's supporters (one die; charge--, EN-=)
            main strike (receiverFor: the defender's support defender
              or the target; hit rate reads the target)
            defender alive? -> the defender's salvo; the counter
              (bearer covers when it holds a charge)
            endActivation: chance step or acted
          turn.Advance(b.state)                        rotations
          encodeResolution
        session.board stays the same object
    response_attacks -> engagement.Menu = Prepare(decision, no
                        response) -> the options from the Plan
    actions / reach -> geometry.ReachableAnchors
    init / load -> board.Load -> assemble for every unit, validate,
                   state.FromContract (the first conversion point)
    export -> board.State -> state.Battle.ToContract (the second)

## Verification

- Gates at every stage in the editors' runs, at 178dec3 in a
  separate subagent run, and at a08ca8e (the editor's run after the
  review fixes): 'gofmt -l' empty, 'go vet' silent, 'go test -race
  ./...' every package ok, 'uv run pytest -q' 1027 then 1029 passed
  4 skipped, ruff clean.
- '/code-review' at high: ten findings. Fixed: the menu gates (1),
  the reach-cells sentinel (2), the Python hello version check (3),
  the intel load (4), the engagement-to-turn import (5), the
  terminology drift (6), the fire predicate (7), the copies of
  'alive'/'livingUnit'/the off-phase text/'cloneAmount' (8), the
  plan's mirror of the receiver (9), the term 'salvo' (10). Not
  done: the two commit bodies that restate the diff (15d62c2,
  c27751f) stay; a rebase would rewrite eleven commits.
- Goldens: 'git diff dev -- tests/fixtures assets/scenarios' shows
  306 removed lines, every one a 'can_counter' line, zero added
  lines; the differential suite passes on the frozen files.
- Test names: 187 on dev, 187 after stage B (none lost, none
  gained), plus the atomicity test and the state clone test after;
  two names changed with their subject when the counter permission
  left ('...NeedsTheReachAndTheEnergy'). The codec decode test died with
  'decodeDecision' at review round 3 (contention point 14).
- The write grep: every assignment to a 'state.Unit' or
  'state.Battle' field outside tests sits in engagement/commit.go or
  turn/turn.go. Every assignment to a 'battle.Unit' or
  'battle.BattleState' field outside tests sits in
  board/resolver.go ('assemble', 'validate'), state/contract.go (the
  conversion) or helpers.go ('Clone').
- The reversal (c4a0edc, 0cc8dc5, d479bb2), measured at this docs
  commit: 'uv run pytest -q' 1034 passed 4 skipped, 'cd engine &&
  go test ./...' every package ok ('def' carries no test file),
  'uv run ruff check src tests scripts' clean. The differential
  suite of 'engine/differential' is one of the green packages, and
  no fixture moved, so the wire form is unchanged.
- The two guard tests of the split: state_test.go partitions the
  fields of 'battle.Unit' over 'state.Unit' and 'state.UnitValue'
  and compares the shape of each pair; contract_test.go fills every
  field through reflection, runs the round trip, proves the answer
  of 'ToContract' shares nothing writable with the state, and proves
  that two units with equal mechs point at two mechs.
- Prepare's check order is today's order statement for statement
  (the editor's report), so every error text and precedence a test
  asserts is unchanged.
- The main session read commit.go in full and the design's
  correspondence in the editors' reports.

## Contention points

1. **'Commit' re-checks a supporter** ('able': alive, a charge, the
   EN) although 'Prepare' proved the charge and the EN. Only
   'alive' can change between the phases (a defender's support
   defender that is also its support attacker may die in the main
   strike). The re-check is the old code's; a reduction to 'alive'
   is a behaviour-neutral cleanup left for the review.
2. **No clone: 'Plan.Draws' bounds the 'outcomes' list.** The board
   counts the chance events of the plan after 'Prepare' and before
   the first write, and refuses a shorter list with
   'ErrOutsideContract' (bad_request). The count reads the plan with
   every unit alive, so a list that would have sufficed on the
   actual path is refused as well: a kill that skips the counter
   still asks for the label of the counter. The Python client sends
   four labels. Both dice modes now run on the session board.
3. **'Apply' removed; 'Advance' stays on the shell** off the
   contract. 'Apply' (prepare and commit with no rotation) existed
   for the 'apply' checks of the frozen golden files
   'engagement_board.json' and 'kill_skill_board.json', on the
   belief that 'Act' would rotate the phase before the comparison.
   'turn.Advance' rotates only when the acting side holds no
   pending unit, and each golden board keeps one such unit on
   purpose (the note in 'resolve_test.go'), so the seventeen checks
   pass through 'Act' unchanged. The board offers one path into the
   engagement, and 'decodeDecision' is private. 'Advance' serves
   'handler.Load': a hand-written snapshot can hold an empty phase.
4. **'state' holds value helpers** ('Unit.Alive',
   'Board.PhaseIndex', 'Footprint.Within' and its kin) although the
   design says "no rule": each reads only the fields of its own
   struct and decides nothing about the battle; the alternative was
   four copies of 'alive' and an engagement-to-turn import. The spec
   names them.
5. **'Menu' returns 'engagement.Options'** because Go forbids a type
   and a function of the same name in one package.
6. **The exit point** is the user's: the attacker's sequence runs
   whole; the defender's reply needs the defender alive; the counter
   needs the attacker alive. The goldens encode all three.
7. **'Prepare' ignores 'Amount', 'Aim' and the dice fields** of the
   decision (skills, map attack) because no rule reads them yet (#81).
8. **'Menu' now refuses what 'act' refuses** (a review fix, a
   behaviour change no golden covers): an off-phase or acted
   attacker, a map weapon, an unpaid weapon, an unreachable
   'move_to', a weapon that fires before a move, a target of the
   attacker's side. 'play.py' catches the refusal and prunes the
   candidate. 'reach' on a destroyed unit is 'ErrDestroyed' now, as
   'actions' already was. Three menu tests were corrected to legal
   attacks (the phase, the move range, the target id); no assertion
   weakened.
9. **'Menu' still measures the distance to the named defender**, not
   to 'plan.target', so a 'defender_id' that is not the target keeps
   today's answer; every caller sends the same id. A refusal when
   they differ would be a new contract rule, left for the review.
10. **'prepareAttack' does not call 'fires'**: its three parts carry
    three error texts and 'destination' runs between the EN check
    and the range check; it shares 'directWeapon' and 'hasENFor'
    with 'fires', which 'counterWeapon', 'supportWeapon' and 'Menu'
    call.

11. **The contract types live in 'engine/battle'** (a user finding
    at review: the wire structures were spread over 'protocol',
    the contract and the board codec, and the contract imported
    the presentation). 'battle' now holds the interfaces and the
    types they speak, with their JSON tags, and imports no package
    of the engine; 'protocol' keeps the envelope, the codes, the
    command wrappers and the one type no contract method speaks
    ('StageEvent') and imports 'battle'. No package of 'battle'
    imports 'protocol': the handler parses 'InitRequest' and passes
    the fields, there is no deploy package, and 'ErrOutsideContract'
    lives in 'engine/battle'. The contract holds one method for the
    content: 'BoardResolver.Load' fills a board for 'init' and for
    'load' alike. There is no factory. The server holds one board,
    and 'main.go' injects it with 'board.New()', the one production
    import of the concrete package. The init handler judges that
    every unit of 'enemies' carries the faction 'enemy', the check
    that the board package ran before. Two behaviors change: the
    load path now judges the units against the bounds, and
    'assemble' runs on both paths but fills only a maximum of zero,
    so a complete snapshot comes back unchanged.
12. **'actions' refuses an acted unit** (protocol 1.6, the user's
    ruling: the embedded error becomes the sentinel). 'Board.Actions'
    reads 'engagement.Activatable', the gate 'act' reads, so an acted
    unit answers 'battle.ErrActed' and the handler maps it to
    'illegal_state', the code 'act' gives for the same error. No
    reader of the old field existed on either side. The handler of
    'actions' keeps its own mapping instead of 'refusalCode': a
    destroyed unit is 'illegal_state' for 'actions' and
    'illegal_action' for 'act', as the spec stated before this
    change; unifying the two is a wire change left for the review.
13. **The contract types are the state** (a user finding at review:
    'state.go' and 'def.go' mirrored the contract types field by
    field, and issue 72 wrote every new field three times). The
    choices the collapse forced, each keeping the wire byte-identical
    (the goldens pass unchanged): 'validate' normalizes a size of 0
    to 1 and an empty terrain to 'space', as the old decode did,
    because 'State' is now 'Clone' and no encode step remains to
    normalize; 'validate' keeps the faction and phase checks for a
    state built without JSON; the footprint-in-bounds check stayed on
    the opening path only until contention point 11 moved it onto
    'Load'; 'TerrainCells' export in payload
    order, not sorted (no golden carries terrain cells); an export
    now echoes a 'null' list that a load carried as 'null' instead
    of '[]' (every golden carries '[]'); 'Clone' shares 'Mech.Weapons'
    with its source, as the old clone shared the definitions, and
    deep-copies 'Bounds', 'TerrainCells' and the event lists that
    'State' now hands out. 'BattleState.TerrainAt'/'TerrainOf' and
    'Skill.Reaches' were written and then removed: no formula reads
    terrain yet (issue 80) and no rule reads a skill range.
    'validate' is private; nothing outside the codec calls it.

14. **The engagement speaks 'battle.Decision'** (a user finding at
    review: 'engagement.Decision', 'engagement.Response' and their
    enums mirrored the contract field by field, and the board
    translated on every call). The mirror types, 'decodeDecision',
    'decodeResponseAttack' and the three enum maps are gone; 'Act'
    and 'ResponseAttacks' pass the payload through, and the
    engagement reads the optional pointer fields through 'nameOf'.
    The codec's two 'ErrOutsideContract' refusals (an unknown kind,
    an unknown stance) fold into the engagement, which answers
    'battle.ErrIllegalAction' from 'Prepare' and from 'answerOf'.
    The wire reaches neither path: the JSON decode of the enums
    refuses first, and no golden changed. The codec test
    'TestTheDecodedActionCarriesTheFieldsOfTheEngagement' died with
    its subject; the standby and reposition tests of 'Prepare' keep
    the tolerance of absent optional fields covered.

15. **The skill carries no area** (a user ruling at review round 3).
    'range_min', 'range_max' and 'blast' left 'battle.Skill' and
    'battle.SkillEntry'. The area of a skill is an arbitrary set of
    cells and can take any shape. The three fields cannot express
    such a shape, so they were the wrong description of the area,
    not an incomplete one. No rule read them. The wire moves to 1.7,
    and the two version constants move together because 'hello'
    refuses a mismatch. The goldens lost 84 key lines and gained
    none: a brace-balanced walk stripped the keys only from the
    objects that hold 'affects'. The replacement representation is
    not decided.

16. **The weapon splits into two types** (a user ruling at review
    round 3, after the skill area). 'battle.Weapon' is a direct
    weapon and 'battle.MapWeapon' is an area weapon; a mech holds
    two lists. The area is the new type 'battle.ShapeRange': a set
    of cell offsets from an origin plus a 'Direction' that turns
    them. A map weapon carries two of them, 'ApplyShape' and
    'EffectShape' (see point 17). 'MapWeaponAffects' is the
    audience, a separate enum from 'SkillAffects' by the user's
    ruling. The wire moves to 1.8 and then to 1.9; both version
    constants move together.
    This version defines the shape and fires nothing: no expansion
    into cells, no rotation, no ammunition spending, no target
    selection, no damage. 'directWeapon' dies, because 'Mech.Weapons'
    holds direct weapons alone. 'WeaponEntry' loses 'ammo': a direct
    weapon spends none, and 'encodeAmmo' now fills
    'MapWeaponEntry.Ammo'.
    The goldens have no writer, so a script moved every weapon object
    with 'map_weapon': true into 'map_weapons' and gave the new
    fields their zero values. The files are byte-identical to their
    canonical JSON dump, which proves the rewrite touched nothing
    else.
    One open point stays for the user: the identifiers of this
    design are the implementing session's proposal, not the user's
    words. The second open point, the integer 'CenterRange' against
    a cell set with holes, is closed by point 17. The panel of the
    game shows no shape at all, so 'WeaponIntel.to_map_weapon'
    writes empty shapes; issue #79 owns the shape source and the
    firing rules.

17. **The map weapon carries two shapes** (a user ruling at review
    round 3, after the weapon split). The user ruled the names.
    'Shape' is now 'ApplyShape' and keeps its meaning. 'Origin' and
    'CenterRange' are both gone, and the new 'EffectShape' takes
    their place; the enum 'MapWeaponOrigin' with 'self' and 'cell'
    is gone with them. The wire moves to 1.9.
    The pitfall: the two names cross over the two columns of the
    datamine. 'ApplyShape' carries 'map_weapon_effect_range', the
    cells that the strike hits. 'EffectShape' carries
    'map_weapon_shooting_range', the cells where the center of the
    strike can sit. A why-comment on each field of 'battle.MapWeapon'
    states the binding, because the name alone reads wrong.
    Why the integer dies: the shooting range has holes. The unit
    1114000250 of the datamine samples is a hollow diamond of reach
    five with the cells inside radius two absent. One integer states
    a full disc, so it states the wrong set.
    The rule that replaces the enum: an empty 'EffectShape.Cells' is
    no choice of center, and the weapon opens its area at the cell of
    the caster. A set that holds cells is a choice.
    Scope is unchanged from point 16: shape only, no firing. No rule
    reads the two fields.
    The goldens moved with the same method as point 16. Every file
    was byte-identical to its canonical JSON dump before the rewrite
    and after it, and 15 map weapon objects changed: 4 in
    'candidate_board.json', 2 in 'debuff_ammo_board.json', 7 in
    'kill_skill_board.json' and 2 in 'response_attack_board.json'.
    Both shapes stay empty there, because no shape source feeds a
    golden.

18. **'def' and 'state' come back** (a user ruling, 2026-08-31).
    Two rulings of this branch conflict across time, and the second
    one wins:
    - 'ef77841' (2026-08-30) deleted the two packages. Its reason:
      "The state and definition packages mirrored the contract types
      field by field, and the board codec copied between the two
      forms in both directions. Every new field, as issue 72 showed,
      was written three times." Contention point 13 records the same
      finding.
    - This ruling writes the two packages again. Its reason: a reader
      cannot see which data a battle changes, because the hit points
      of a unit and the move range of its mech sit in one flat
      struct.
    What makes the second attempt different: 'engine/battle' imports
    no package of the engine. 'def' and 'state' both import it and
    reuse its vocabulary word for word. The deleted 'state.go'
    re-declared 'Cell', 'Size', 'Footprint', 'Bounds', 'Faction',
    'Terrain', 'Debuff', 'Skill' and the skill enums, and the deleted
    'def.go' re-declared 'WeaponCategory' and wrapped a pair of
    integers in 'RadiusRange'. The new 'state.go' declares three
    types and re-declares nothing; the new 'def.go' declares six and
    re-declares nothing. The mirror is gone; the split is not.
    The cost, stated plainly. A new dynamic field of a unit is now
    written in four places: 'battle.Unit' in snapshot.go, 'UnitValue'
    in state.go, and one line in each direction of contract.go. A new
    field of a mech, a pilot or a weapon is also four, because 'def'
    holds distinct types. Three of the four fail loudly:
    - state_test.go partitions the fields. A field of 'battle.Unit'
      that sits in no state struct fails, and a field of the state
      that sits in no field of 'battle.Unit' fails as well. The test
      also compares the shape of each pair.
    - contract_test.go fills every field through reflection and runs
      the round trip. A dropped line of either direction fails and
      names the field it dropped.
    The fourth place, which half of a new field belongs in, is a
    judgment that no test makes. The placement rule for the reviewer:
    'UnitValue' holds every field that a rule of a battle writes,
    plus the three pools a unit spends ('SP', 'Ammo', 'Skills'). A
    maximum is the bound of a pool and not a pool, so it stands for
    the whole battle and sits on 'state.Unit'.
    Distinct 'def' types, not aliases of the contract types (the
    user's ruling). The price of the distinct types is the four-place
    cost above on every static field. The price of an alias is that
    'def.Weapon' would carry the JSON tags of the wire, so a wire
    rename would reshape the definition in silence and the two layers
    would be one type with two names. The user paid the first price.
    Three more rulings ride with this one:
    - 'state' stays internal. The contract keeps 'battle.Unit', and
      the conversion happens at two points only: 'Load' and 'State'.
    - A named field, not an embedded struct: 'unit.Value.HP', never
      'unit.HP'. The user chose the larger edit so that a reader sees
      which data changes.
    - The unit layer only. 'battle.BattleState' is not wrapped this
      time: 'state.Battle' is a distinct type, and its units are the
      split ones.
    Contention point 4 stands again: 'state' holds value helpers
    ('Unit.Alive', 'Battle.PhaseIndex', 'Unit.Footprint'). Each one
    reads only the fields of its own struct and decides nothing about
    the battle. 'Weapon.Reaches' and 'Weapon.Debuff' moved to
    'def.Weapon' for the same reason. 'battle.BattleState.Clone'
    stays on the contract and is the one deep copy of the engine.

19. **The skill gets an area, and 'AffectArea' holds it for both
    owners** (a user ruling, 2026-08-31). Protocol 1.9 to 1.10.
    The skill carried no area at all. '6af4a7b' removed 'range_min',
    'range_max' and 'blast' from it, and nothing took their place.
    This change is that replacement, not a revert of '6af4a7b': the
    three removed fields state a range band with a radius, and the
    area of a skill is an arbitrary set of cells that no band can
    state. The skill now carries the same pair the map weapon got at
    'a429965'.
    The datamine proves the shape and the naming. The supporter
    ability 1001000150 of
    'docs/reference/datamine-samples/202608161248/supporter/' has the
    description "Allies in range: Restore EN by 50%" and the column
    'effect_range' with a diamond of radius four that holds the
    origin (0,0). It carries no shooting range of its own, so it is
    the caster-centered case that an empty 'EffectShape' already
    states on a map weapon.
    Mid-task ruling, folded into the same pass: the pair goes in one
    type, 'AffectArea', and 'MapWeapon' and 'Skill' share it, in
    'battle' and in 'def' alike. The reasons: the pair carries one
    rule; the crossover comment now stands once instead of twice; two
    adjacent parameters of one type invite a swapped call when a
    later issue implements the expansion.
    An anonymous embedded field, not a named one. 'encoding/json'
    flattens it at its position, so the wire keeps 'apply_shape' and
    'effect_shape' flat and in the same order, and field promotion
    keeps 'weapon.ApplyShape' working. Verified by encoding
    'MapWeapon', 'Skill', 'SkillEntry' and 'MapWeaponEntry' before
    and after the wrapping: the two dumps are byte-identical.
    Two review points for the reader:
    - A composite literal cannot name a promoted field. Four
      conversion functions in 'contract.go' and three Go test
      literals now name 'AffectArea'. That is the whole cost.
    - The Go-to-Python field-order gate in
      'tests/test_engine_codec.py' parses the JSON tags of
      'snapshot.go' line by line. An embedded field carries no tag,
      so the parser dropped both keys and the gate failed. The parser
      now records an embedded member and flattens it at its position,
      the way 'encoding/json' does. It was not un-embedded to dodge
      the gate.
    The partition test of 'state_test.go' needed no change: it reads
    an embedded field as one field named 'AffectArea' on both sides
    and recurses into it. The deliberate failure is on record: with
    the fields on 'battle.Skill' alone, it reported 'the field
    "Skills" carries []battle.Skill in the contract and []def.Skill
    in the state'.
    'SkillEntry' and 'MapWeaponEntry' in 'responses.go' keep two flat
    fields and embed nothing. The ruling named the four definition
    types, and an entry is built with named fields at one call site,
    so it carries no swapped-call risk.
    28 skill objects gained the two keys, each an empty cell list
    with a direction of 'none': 10 in 'candidate_board.json', 14 in
    'kill_skill_board.json' and 4 in 'debuff_ammo_board.json'. No
    shape source feeds a golden.
    No rule reads either field, exactly as with the map weapon.

## Deferred

- #72 on this structure: the ability fields on the contract types
  and on 'def', the pure system 'abilities', the assembly reading
  the abilities, 'engagement' reading the modified stats; the
  catalog, the converter and the docs from the #72 branch. Each new
  field costs the four places of contention point 18.
- 'nearestFreeCell' in geometry has no caller outside its tests
  (as on dev).
- The Python sandbox and the fake server: unchanged by the wire
  removal except the key.

