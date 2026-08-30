# Branch roadmap: issue 88, the battle engine as definitions, state and systems

> Type: working—deleted at merge

Issue: #88. Branch: issue-88-engine-restructure. Status: awaiting-review.
Base: dev c65f416. The #72 branch (issue-72-mech-pilot-unit, head
9cad225) is the source of parts for #72 after this branch merges.

## Design (approved before code)

Three kinds of package below the contract 'engine/battle', and one
shell. Imports run one way: shell -> systems -> state -> def ->
formula. A system never imports another system except through the
pure ones (geometry).

### Static definitions: 'engine/battle/def'

Immutable after decode. Exported fields. Shared by pointer between
every clone of a board.

    type Mech struct {
        HP, EN                      int
        Attack, Defense, Mobility   float64
        MoveRange                   int
        Weapons                     []Weapon
    }
    type Pilot struct {
        Ranged, Melee, Awaken, Defense, Reaction float64
        SP                                      int
    }
    type Weapon struct {
        Name            string
        Power           float64
        Range           RadiusRange
        ENCost          int
        Accuracy        float64
        MapWeapon       bool
        UsableAfterMove bool
        DebuffKind      string
        DebuffMagnitude float64
        Categories      []WeaponCategory
    }
    type RadiusRange struct{ Min, Max int }   // Holds(distance int) bool
    type WeaponCategory string                // ranged, melee, awaken

No 'CanCounter': a counter fires under the rule of an attack (user
ruling 2026-08-30). The ability fields of #72 land here later.

### Dynamic state: 'engine/battle/state'

Small structs, exported fields, no methods that decide anything.
'Board.Clone' copies the units and their slices and maps; the
definitions stay shared.

    type Unit struct {
        ID        string
        Faction   Faction
        Footprint Footprint
        Mech      *def.Mech
        Pilot     *def.Pilot
        HP, MaxHP, EN, ENMax, SP, SPMax int
        Acted     bool
        ChanceSteps, ChanceStepsMax                     int
        SupportDefendCharges, SupportDefendChargesMax   int
        SupportAttackCharges, SupportAttackChargesMax   int
        HasShield, SupportDefendWhenAttack              bool
        Ammo      map[string]int
        Debuffs   []Debuff
        Skills    []Skill        // per-unit wire data; no rule reads it (#81)
    }
    type Board struct {
        Bounds         Bounds
        Units          []Unit
        Phase          Faction
        Turn           int
        DefaultTerrain Terrain
        TerrainCells   map[Cell]Terrain
    }
    // Vocabulary of the grid: Cell, Size, Footprint, Bounds, Faction,
    // Terrain, Debuff, Skill and the skill enums.
    func (b *Board) Unit(id string) *Unit      // lookup, nil when absent
    func (b *Board) Clone() Board

### Pure systems (read, never write)

'engine/battle/geometry':

    func Distance(a, b state.Footprint) int
    func FootprintAt(unit *state.Unit, anchor state.Cell) state.Footprint
    func Within(f state.Footprint, bounds state.Bounds) bool
    func Occupied(board *state.Board, except string) CellSet
    func Blocking(board *state.Board, unit *state.Unit) CellSet
    func ReachableAnchors(board *state.Board, unit *state.Unit) CellSet
    func SortedCells(set CellSet) []state.Cell

'engine/battle/abilities' arrives with #72 (condition sums, scaled
stats); in this issue the maxima come from the definitions alone.

### Writing systems

'engine/battle/engagement' — one activation of one unit: the move,
the exchange, the end of the activation.

    type Decision struct {          // the domain form of protocol.Decision
        UnitID   string
        Kind     ActionKind         // attack, map_attack, reposition, standby
        MoveTo   *state.Cell
        TargetID string
        Weapon   string
        SupportDefender  string
        SupportAttackers []string
        Response *Response
    }
    type Response struct {
        Stance           Stance
        Weapon           string
        SupportDefender  string
        SupportAttackers []string
    }

    // Prepare validates every participant and writes nothing. Every
    // error of 'Act' comes from here: battle.ErrNoUnit, ErrDestroyed,
    // ErrOffPhase, ErrActed, ErrIllegalMove, ErrIllegalAction.
    func Prepare(board *state.Board, decision Decision) (Plan, error)

    // Plan is the ordered list of steps with every choice resolved:
    // the anchor, the target, the weapon, each supporter with its
    // weapon and distance, the bearer, the stance, the counter weapon.
    type Plan struct { ... unexported ... }

    // Commit writes the plan in order and cannot fail. It stops when
    // the receiver of the next strike is destroyed; a shooter that
    // died earlier in the exchange is skipped.
    func Commit(board *state.Board, plan Plan, dice battle.Dice) Trace

    // Menu answers 'response_attacks' with the same eligibility
    // helpers Prepare uses, so the menu and the check never diverge.
    func Menu(board *state.Board, decision Decision, defenderID string) (Menu, error)

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

    func Advance(board *state.Board) []Rotation     // phase rotation,
        // EN regeneration, debuff expiry, acted reset, as turn.go today

'engine/battle/deploy':

    func Assemble(unit *state.Unit)   // maxima from the definitions
        // (fillMaxima today); #72 adds the abilities
    // 'Place' comes with #72.

### The shell: 'engine/battle/board'

    type Board struct{ state state.Board }   // implements battle.Board
    DecodeInit, DecodeState                  // wire -> def + state
    Act: decode -> engagement.Prepare -> engagement.Commit ->
         turn.Advance -> encode. Atomic by construction: Prepare
         returns before the first write and Commit cannot fail, so
         handler/act.go drops its clone.
    Capabilities, ReachableCells: geometry
    ResponseAttacks: engagement.Menu
    Clone: state.Board.Clone
    State, Summary: encode

The codec (wire <-> def/state) stays in the shell in two files: one
for the definitions, one for the state. Every parse of a wire name
lives there.

### Rule of writes

Only 'engagement.Commit', 'turn.Advance', 'deploy.Assemble' and the
shell's decoders assign a field of 'state.Unit' or 'state.Board'.
Review check: grep for assignments to those fields outside the three
systems and the codec files.

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
  (this commit). Every stage: gates green, goldens byte-identical
  apart from the removed key.

## Change summary

| Commit | What |
|---|---|
| 2015ab0, c7dbd1a | The design and the ledger entries of the 0830 rulings |
| c27751f | 'engine/battle/def' and 'engine/battle/state'; the board decodes into them ('def_codec.go' for the definitions) |
| 077f5d1 | 'engine/battle/geometry'; the board reads it |
| 1e2fa3a | The state clone test: definitions shared, state copied |
| 373a69d | 'engine/battle/engagement' ('Prepare', 'Commit', 'Menu', the decision and result types), 'engine/battle/turn' ('Advance', 'PhaseIndex', 'Pending', 'Gone'), 'engine/battle/deploy' ('Assemble'); the board still drove the old flow |
| 15d62c2 | The board reduced to the shell: 'Act' = 'Prepare', 'Commit', 'turn.Advance'; resolve.go, strike.go, forecast.go, response_attacks.go, results.go, turn.go, model.go deleted; tests moved |
| 04dbde7 | The handler runs 'Act' on the session board; a clone only on the forced-dice path; the atomicity test |
| 6e943b2 | 'can_counter' removed from the definitions, the codecs, the wire (protocol 1.5), the Python mirror, the fixtures (306 lines) and the scenario placeholder |
| 2d5e28f | The counter rule and the 1.5 entry in the spec; the datamine note |
| (this) | The spec process model, the terminology rows, this artifact |

    engine/battle/def         def.go (55)
    engine/battle/state       state.go (193): Unit, Board, the grid
                              vocabulary, Clone
    engine/battle/geometry    geometry.go (138)
    engine/battle/engagement  model.go (Decision, Response, Plan),
                              prepare.go (279), commit.go (177),
                              menu.go (114), strike.go (104),
                              support.go (53), forecast.go, results.go
    engine/battle/turn        turn.go (118)
    engine/battle/deploy      deploy.go (20)
    engine/battle/board       board.go (139), codec.go, def_codec.go,
                              candidates.go, clone.go
    engine/server/handler     act.go
    engine/protocol           state.go, types.go, envelope.go (1.5)
    src/ggge_ai/engine        state.py, codec.py, contract.py (1.5)

## Call chain

    act {unit_id, action, response_attack, dice}
      handler.Commands.Act
        target = session board (a clone only when the dice are forced)
        board.Act(decision, dice)                       the shell
          DecodeDecision -> engagement.Decision
          engagement.Prepare(state, decision)           reads only
            actor: exists, alive, of the phase, not acted
            kind: attack | reposition | standby (map_attack refused)
            anchor: reachable (geometry), permitted after the move
            attack: target (alive, opposing), weapon (not map, exists),
              EN, reach (geometry.Distance), the actor's supporters
              (<= 3, unique, eligible), the bearer, the response
              (stance, counter weapon, support defender, the
              defender's supporters)
            -> Plan, or the first error
          engagement.Commit(state, plan, dice)          writes, cannot fail
            anchor; actor.EN -= cost
            salvo of the actor's supporters (one die; charge--, EN-=)
            main strike (receiver = the defender's support defender
              or the target; hit rate reads the target)
            defender alive? -> the defender's salvo; the counter
              (bearer covers when it holds a charge)
            endActivation: chance step or acted
          turn.Advance(state)                           rotations
          encodeResolution
        session.board stays the same object
    response_attacks -> engagement.Menu(state, decision, defender)
    actions / reach -> geometry.ReachableAnchors
    init -> decode -> deploy.Assemble for every unit

## Verification

- Gates at every stage in the editors' runs and at the final head in
  a separate subagent run: 'gofmt -l' empty, 'go vet' silent, 'go
  test -race ./...' every package ok, 'uv run pytest -q' 1027
  passed 4 skipped, ruff clean.
- Goldens: 'git diff dev -- tests/fixtures assets/scenarios' shows
  306 removed lines, every one a 'can_counter' line, zero added
  lines; the differential suite passes on the frozen files.
- Test names: 187 on dev, 187 after stage B (none lost, none
  gained), plus the atomicity test and the state clone test after;
  two names changed with their subject when the counter permission
  left ('...NeedsTheReachAndTheEnergy').
- The write grep: every assignment to a 'state.Unit' or
  'state.Board' field outside tests sits in engagement/commit.go,
  turn/turn.go, deploy/deploy.go, board/codec.go or
  state/state.go (its own 'Clone').
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
2. **The forced-dice path keeps a clone in the handler.** A manual
   'outcomes' list is short only when a draw runs past its end,
   which 'Commit' learns during the roll; the refusal must leave
   the board unchanged, so that path clones. Sampled dice, the
   production path, run on the session board.
3. **'Apply' and 'Advance' stay on the shell** beside 'Act':
   'engine/differential' drives 'Apply' (no rotation, the oracle
   rotates itself) and 'handler.Load' calls 'Advance' on a snapshot.
   Both are one-line delegations.
4. **The off-phase message text is in two packages**
   ('board/candidates.go' for 'actions', 'engagement/prepare.go' for
   'act'); 'capabilities' needs living and on-phase but not the
   acted gate, so no shared helper served both.
5. **'Menu' returns 'engagement.Options'** because Go forbids a type
   and a function of the same name in one package.
6. **The exit point** is the user's: the attacker's sequence runs
   whole; the defender's reply needs the defender alive; the counter
   needs the attacker alive. The goldens encode all three.
7. **'Decision' keeps 'Amount' and 'Aim'** (skills, map attack)
   although no rule reads them yet (#81).

## Deferred

- #72 on this structure: the ability fields on 'def', the pure
  system 'abilities', 'deploy.Assemble' reading the abilities,
  'engagement' reading the modified stats; the catalog, the
  converter and the docs from the #72 branch.
- 'nearestFreeCell' in geometry has no caller outside its tests
  (as on dev).
- The Python sandbox and the fake server: unchanged by the wire
  removal except the key.

